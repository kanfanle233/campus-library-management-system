"""CSV import and export use cases.

The service owns the import transaction.  Repositories and read queries do
not commit, so a valid file is either fully inserted or leaves the database
unchanged.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import FineStatus, LoanStatus, UserRole
from app.core.exceptions import ValidationAppError
from app.database import begin_immediate
from app.models import Book, Loan, User
from app.schemas.book import BookCreate
from app.schemas.file import FileImportError, FileImportResult
from app.services.fine_service import calculate_fine_cents, calculate_overdue_days, format_cents


BOOK_CSV_HEADERS = (
    "title",
    "author",
    "isbn",
    "publisher",
    "price",
    "total_quantity",
    "category",
)
BOOK_CSV_HEADERS_QUANTITY_ALIAS = (
    "title",
    "author",
    "isbn",
    "publisher",
    "price",
    "quantity",
    "category",
)

# Keep all export columns explicit.  In particular, password_hash is never
# selected or passed to the CSV writer.
BOOK_EXPORT_HEADERS = (
    "book_code",
    "title",
    "author",
    "isbn",
    "publisher",
    "price",
    "total_quantity",
    "available_quantity",
    "category",
    "is_active",
)
READER_EXPORT_HEADERS = (
    "id",
    "login_name",
    "student_id",
    "name",
    "contact",
    "borrow_limit",
    "role",
    "is_active",
    "created_at",
    "updated_at",
)
LOAN_EXPORT_HEADERS = (
    "loan_no",
    "student_id",
    "book_code",
    "borrow_date",
    "due_date",
    "return_date",
    "overdue_days",
    "fine_amount",
    "status",
    "fine_status",
)

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 1000


def _error(row: int, reason: str) -> FileImportError:
    return FileImportError(row=row, reason=reason)


def _validation_reason(exc: Exception) -> str:
    """Flatten Pydantic's structured errors into a stable, useful message."""

    errors = getattr(exc, "errors", lambda: [])()
    parts: list[str] = []
    for item in errors:
        location = item.get("loc", ())
        field = str(location[-1]) if location else "row"
        message = str(item.get("msg", "invalid value"))
        parts.append(f"{field}: {message}")
    return "; ".join(parts) or str(exc)


def _safe_cell(value: Any) -> Any:
    """Escape spreadsheet formula prefixes without changing numeric cells."""

    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_bytes(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> bytes:
    # newline="" is required by the csv module so quoted newlines are emitted
    # as valid CSV records on every platform. utf-8-sig supplies the BOM.
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_safe_cell(value) for value in row])
    return output.getvalue().encode("utf-8-sig")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (FineStatus, UserRole, LoanStatus)):
        return value.value
    return str(value)


class FileService:
    """Coordinate CSV validation, persistence and export queries."""

    @staticmethod
    def parse_books_csv(content: bytes) -> tuple[list[tuple[int, dict[str, str]]], list[FileImportError]]:
        """Decode and parse all rows before any database write occurs."""

        errors: list[FileImportError] = []
        try:
            # utf-8-sig accepts ordinary UTF-8 and strips a leading BOM.
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            return [], [_error(1, "文件必须是 UTF-8 编码")]

        reader = csv.reader(StringIO(text, newline=""), strict=True)
        try:
            header = next(reader)
        except StopIteration:
            return [], [_error(1, "CSV 文件不能为空")]
        except csv.Error as exc:
            return [], [_error(1, f"CSV 格式错误: {exc}")]

        if header == list(BOOK_CSV_HEADERS_QUANTITY_ALIAS):
            parse_headers = BOOK_CSV_HEADERS_QUANTITY_ALIAS
        elif header == list(BOOK_CSV_HEADERS):
            parse_headers = BOOK_CSV_HEADERS
        else:
            return [], [
                _error(
                    1,
                    "表头必须为: "
                    f"{','.join(BOOK_CSV_HEADERS)}（quantity 也可作为数量列）",
                )
            ]

        rows: list[tuple[int, dict[str, str]]] = []
        try:
            for row in reader:
                row_number = reader.line_num
                if not row or all(not cell.strip() for cell in row):
                    errors.append(_error(row_number, "空数据行"))
                    continue
                if len(rows) >= MAX_IMPORT_ROWS:
                    errors.append(_error(row_number, f"最多导入 {MAX_IMPORT_ROWS} 行"))
                    # One explicit limit error is enough; no rows after the
                    # limit can be inserted either.
                    break
                if len(row) != len(parse_headers):
                    errors.append(_error(row_number, "列数与表头不一致"))
                    continue
                values = dict(zip(parse_headers, row))
                # BookCreate uses the clearer database name internally while
                # accepting the course wording ``quantity`` in CSV files.
                if "quantity" in values:
                    values["total_quantity"] = values.pop("quantity")
                rows.append((row_number, values))
        except csv.Error as exc:
            errors.append(_error(reader.line_num or 1, f"CSV 格式错误: {exc}"))
        return rows, errors

    def import_books(self, session: Session, content: bytes) -> FileImportResult:
        if len(content) > MAX_FILE_BYTES:
            raise ValidationAppError("文件大小不能超过 2 MiB")

        rows, parse_errors = self.parse_books_csv(content)
        total = len(rows) + len({item.row for item in parse_errors if item.row > 1})
        # Include malformed/empty rows in total, while avoiding counting the
        # header-level error as a data row.
        if not rows and not parse_errors:
            total = 0
        errors = list(parse_errors)
        payloads: list[tuple[int, BookCreate]] = []
        seen: dict[str, int] = {}
        for row_number, values in rows:
            try:
                payload = BookCreate.model_validate(values)
            except Exception as exc:
                errors.append(_error(row_number, _validation_reason(exc)))
                continue
            isbn = payload.isbn
            if isbn in seen:
                errors.append(_error(row_number, f"ISBN 重复（与第 {seen[isbn]} 行重复）"))
                continue
            seen[isbn] = row_number
            payloads.append((row_number, payload))

        # A header, encoding or row-level error prevents every write.  This
        # is deliberately decided before BEGIN IMMEDIATE is called.
        if errors:
            return FileImportResult(total=total, success=0, failed=len(errors), errors=errors)

        # A dependency may have performed the authentication SELECT already,
        # leaving a read transaction open. End it before taking the writer
        # lock required by the import contract.
        if session.in_transaction():
            session.rollback()
        begin_immediate(session)
        try:
            books: list[Book] = []
            for index, (row_number, payload) in enumerate(payloads):
                if session.scalar(select(Book.id).where(Book.isbn == payload.isbn)) is not None:
                    errors.append(_error(row_number, "ISBN 已存在"))
                    continue
                total_quantity = payload.total_quantity
                if total_quantity is None:
                    # BookCreate's model validator normally fills this value.
                    total_quantity = payload.quantity or 0
                book = Book(
                    # book_code is unique, so use a distinct temporary value
                    # while several new rows are flushed together.  Every
                    # row receives its public BK number immediately after
                    # SQLAlchemy assigns its database id.
                    book_code=f"PENDING-{index}",
                    title=payload.title,
                    author=payload.author,
                    isbn=payload.isbn,
                    publisher=payload.publisher,
                    price_cents=int(payload.price * 100),
                    total_quantity=total_quantity,
                    available_quantity=total_quantity,
                    category=payload.category,
                    is_active=True,
                )
                session.add(book)
                books.append(book)
            if errors:
                session.rollback()
                return FileImportResult(total=total, success=0, failed=len(errors), errors=errors)

            session.flush()
            for book in books:
                book.book_code = f"BK{book.id:06d}"
            session.flush()
            session.commit()
            return FileImportResult(total=total, success=len(books), failed=0, errors=[])
        except IntegrityError as exc:
            session.rollback()
            # The pre-check above is deterministic under BEGIN IMMEDIATE, but
            # retain a stable report if a database constraint still wins.
            reason = "ISBN 已存在" if "isbn" in str(exc).lower() else "数据写入失败"
            row_number = payloads[0][0] if payloads else 2
            return FileImportResult(
                total=total,
                success=0,
                failed=1,
                errors=[_error(row_number, reason)],
            )
        except Exception:
            session.rollback()
            raise

    def export_books(self, session: Session) -> bytes:
        books = session.scalars(select(Book).order_by(Book.id)).all()
        rows = (
            (
                book.book_code,
                book.title,
                book.author,
                book.isbn,
                book.publisher,
                f"{Decimal(book.price_cents) / Decimal(100):.2f}",
                book.total_quantity,
                book.available_quantity,
                book.category,
                book.is_active,
            )
            for book in books
        )
        return _csv_bytes(BOOK_EXPORT_HEADERS, rows)

    def export_readers(self, session: Session) -> bytes:
        readers = session.scalars(select(User).where(User.role == UserRole.READER).order_by(User.id)).all()
        rows = (
            (
                reader.id,
                reader.login_name,
                reader.student_id,
                reader.name,
                reader.contact,
                reader.borrow_limit,
                _text(reader.role),
                reader.is_active,
                _text(reader.created_at),
                _text(reader.updated_at),
            )
            for reader in readers
        )
        return _csv_bytes(READER_EXPORT_HEADERS, rows)

    def export_loans(self, session: Session, *, as_of: date | None = None) -> bytes:
        today = as_of or date.today()
        rows = session.execute(
            select(Loan, User, Book)
            .join(User, Loan.reader_id == User.id)
            .join(Book, Loan.book_id == Book.id)
            .order_by(Loan.id)
        ).all()

        def values():
            for loan, reader, book in rows:
                effective_date = loan.return_date if loan.status is LoanStatus.RETURNED and loan.return_date else today
                fine_cents = loan.fine_cents if loan.status is LoanStatus.RETURNED else calculate_fine_cents(loan.due_date, today)
                yield (
                    loan.loan_no,
                    reader.student_id,
                    book.book_code,
                    _text(loan.borrow_date),
                    _text(loan.due_date),
                    _text(loan.return_date),
                    calculate_overdue_days(loan.due_date, effective_date),
                    format_cents(fine_cents),
                    _text(loan.status),
                    _text(loan.fine_status),
                )

        return _csv_bytes(LOAN_EXPORT_HEADERS, values())


file_service = FileService()


# Functional entry points keep the module convenient for small integrations.
def import_books(session: Session, content: bytes) -> FileImportResult:
    return file_service.import_books(session, content)


def export_books(session: Session) -> bytes:
    return file_service.export_books(session)


def export_readers(session: Session) -> bytes:
    return file_service.export_readers(session)


def export_loans(session: Session, *, as_of: date | None = None) -> bytes:
    return file_service.export_loans(session, as_of=as_of)
