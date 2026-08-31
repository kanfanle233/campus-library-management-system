from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Book, Loan, User


def _run_seed(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "scripts.seed", *args],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )


def test_seed_counts_codes_dates_inventory_and_is_idempotent(tmp_path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'seed.sqlite3'}"
    first = _run_seed(database_url, "--as-of", "2026-08-31")
    second = _run_seed(database_url, "--as-of", "2026-08-31")

    assert "演示数据已写入" in first.stdout
    assert "已存在，跳过" in second.stdout
    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            assert session.scalar(select(User).where(User.login_name == "admin")).name == "DEMO管理员"
            assert session.query(User).count() == 9
            assert session.query(Book).count() == 15
            assert session.query(Loan).count() == 12
            assert [book.book_code for book in session.scalars(select(Book).order_by(Book.id))][:2] == ["BK000001", "BK000002"]
            assert session.scalar(select(Book).where(Book.book_code == "BK000001")).isbn == "978DEMO000001"
            assert [loan.loan_no for loan in session.scalars(select(Loan).order_by(Loan.id))][:2] == ["LN000001", "LN000002"]
            for loan in session.scalars(select(Loan)):
                assert (loan.due_date - loan.borrow_date).days == 30
            for book in session.scalars(select(Book)):
                active = sum(loan.status.value == "BORROWED" for loan in book.loans)
                assert book.available_quantity == book.total_quantity - active
            assert any(book.available_quantity == 0 for book in session.scalars(select(Book)))
    finally:
        engine.dispose()
