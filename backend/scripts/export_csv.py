"""Write the three administrator CSV exports to a local directory."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from app.database import SessionLocal
from app.services.file_service import file_service


def export_files(output_dir: str | Path, *, as_of: date | None = None) -> list[Path]:
    """Generate UTF-8-BOM CSV files and return their paths."""

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as session:
        contents = {
            "books.csv": file_service.export_books(session),
            "readers.csv": file_service.export_readers(session),
            "loans.csv": file_service.export_loans(session, as_of=as_of),
        }
    paths: list[Path] = []
    for filename, content in contents.items():
        path = destination / filename
        path.write_bytes(content)
        paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="导出图书管理系统 CSV 文件")
    parser.add_argument(
        "--output-dir",
        default="data/exports",
        help="输出目录，默认是 backend/data/exports",
    )
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today(), metavar="YYYY-MM-DD")
    args = parser.parse_args()
    for path in export_files(args.output_dir, as_of=args.as_of):
        print(f"已写出 {path}")


if __name__ == "__main__":
    main()
