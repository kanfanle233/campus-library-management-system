-- Library Management System (SQLite)
-- This file mirrors the SQLAlchemy models. `python -m scripts.init_db`
-- is the normal idempotent entry point for creating the same schema.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
    id INTEGER NOT NULL PRIMARY KEY,
    book_code VARCHAR(64) NOT NULL,
    title VARCHAR(255) NOT NULL,
    author VARCHAR(255) NOT NULL,
    isbn VARCHAR(32) NOT NULL,
    publisher VARCHAR(255),
    price_cents INTEGER NOT NULL DEFAULT 0 CHECK (price_cents >= 0),
    category VARCHAR(100),
    total_quantity INTEGER NOT NULL DEFAULT 0 CHECK (total_quantity >= 0),
    available_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (available_quantity >= 0)
        CHECK (available_quantity <= total_quantity),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE (book_code),
    UNIQUE (isbn)
);

CREATE INDEX IF NOT EXISTS ix_books_title ON books (title);
CREATE INDEX IF NOT EXISTS ix_books_author ON books (author);
CREATE INDEX IF NOT EXISTS ix_books_category ON books (category);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER NOT NULL PRIMARY KEY,
    login_name VARCHAR(64) UNIQUE,
    student_id VARCHAR(64) UNIQUE,
    name VARCHAR(100) NOT NULL,
    contact VARCHAR(100),
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(6) NOT NULL DEFAULT 'READER'
        CHECK (role IN ('ADMIN', 'READER')),
    borrow_limit INTEGER NOT NULL DEFAULT 5 CHECK (borrow_limit >= 0),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    id INTEGER NOT NULL PRIMARY KEY,
    loan_no VARCHAR(64) NOT NULL UNIQUE,
    reader_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE RESTRICT,
    borrow_date DATE NOT NULL,
    due_date DATE NOT NULL CHECK (due_date >= borrow_date),
    return_date DATE,
    status VARCHAR(8) NOT NULL DEFAULT 'BORROWED'
        CHECK (status IN ('BORROWED', 'RETURNED')),
    fine_cents INTEGER NOT NULL DEFAULT 0 CHECK (fine_cents >= 0),
    fine_status VARCHAR(6) NOT NULL DEFAULT 'NONE'
        CHECK (fine_status IN ('NONE', 'UNPAID', 'PAID')),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CHECK (
        (status = 'BORROWED' AND return_date IS NULL)
        OR (status = 'RETURNED' AND return_date IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS ix_loans_reader_status ON loans (reader_id, status);
CREATE INDEX IF NOT EXISTS ix_loans_book_status ON loans (book_id, status);
CREATE INDEX IF NOT EXISTS ix_loans_status ON loans (status);
CREATE INDEX IF NOT EXISTS ix_loans_fine_status ON loans (fine_status);
