Library Management System backend
=================================

This backend implements the course assessment requirements with Python,
FastAPI, SQLAlchemy and SQLite.  The API uses `/api/v1`; interactive API
documentation is available at `/docs` while the server is running.

Requirements
------------

* Python 3.10 or newer
* A local SQLite database (no separate database server is required)

Install and run
---------------

From this `backend` directory:

    /opt/miniconda3/envs/pytorch_env/bin/python -m pip install -r requirements.txt
    cp .env.example .env
    # Set a private JWT_SECRET_KEY in .env before sharing the project.
    /opt/miniconda3/envs/pytorch_env/bin/python -m scripts.init_db
    /opt/miniconda3/envs/pytorch_env/bin/python -m scripts.seed --as-of 2026-08-31
    /opt/miniconda3/envs/pytorch_env/bin/python -m uvicorn app.main:app --reload --port 8000

The demo administrator is `admin` / `admin123`.  Demo readers use their
student ID (for example `DEMO-S001`) and password `demo123`.  These credentials
are synthetic local-demo data.  Running `scripts.seed` again never clears or
overwrites an existing database.

Implemented API areas
---------------------

* `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
* `GET/POST /api/v1/books`, `GET/PATCH/DELETE /api/v1/books/{id}`
* `GET/POST /api/v1/readers`, `GET/PATCH/DELETE /api/v1/readers/{id}`
* `GET /api/v1/loans`, `POST /api/v1/loans/borrow`
* `GET /api/v1/loans/{id}`, receipt, return preview, return and fine payment
* Administrator CSV book import and books/readers/loans export under
  `/api/v1/files`
* Administrator summary at `/api/v1/dashboard/stats`
* Administrator analytics at `/api/v1/dashboard/analytics?days=7|30|90`,
  including zero-filled daily borrow/return trends, category inventory,
  popular books and current overdue buckets

Borrowing uses a 30-calendar-day loan period.  An overdue loan blocks a new
borrow for that reader.  A return records `overdue_days` and a fine of 0.10
yuan per overdue day, and adjusts available inventory in the same SQLite
transaction as the loan state change.  SQLite foreign keys, WAL mode, a busy
timeout and `BEGIN IMMEDIATE` are enabled for write operations.

CSV import and export
---------------------

Book imports are UTF-8/UTF-8-BOM CSV files with the exact columns:

    title,author,isbn,publisher,price,total_quantity,category

The quantity column may also be named `quantity` for a course worksheet; it is
normalized to `total_quantity` internally.

The whole file is validated before it is committed.  The limit is 2 MiB and
1,000 data rows.  Export files include only public reader fields; password
hashes are never exported.  Spreadsheet formula prefixes are escaped on
export.

For a local file-write demonstration, run:

    /opt/miniconda3/envs/pytorch_env/bin/python -m scripts.export_csv --output-dir data/exports --as-of 2026-08-31

Tests and course evidence
-------------------------

From the project root, run:

    /opt/miniconda3/envs/pytorch_env/bin/python -m pytest -q backend/tests
    /opt/miniconda3/envs/pytorch_env/bin/python -m compileall -q backend/app backend/scripts

The test suite covers authentication, reader CRUD and deactivation rules,
book CRUD/search/inventory rules, atomic borrow/return/fine calculations,
dashboard aggregates, seed idempotence, and CSV validation/export.  The
`backend/database/schema.sql` file is the submitted database schema; the
`backend/scripts/init_db.py` and `backend/scripts/seed.py` files are the
initialization scripts.  For the report, capture screenshots of `/docs`,
the frontend API calls, the before/after CSV files, and the generated receipt.

The course also requires a frontend and a 10-page technical report.  The
repository's `frontend` directory supplies a Google-style React interface and
can run in a no-backend demo mode for static hosting.  Real database writes
still require the local FastAPI server unless a separate backend deployment is
configured.
