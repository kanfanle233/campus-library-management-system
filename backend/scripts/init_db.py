"""Create the library schema without changing existing rows."""

from app.database import init_db


def main() -> None:
    init_db()
    print("数据库表已初始化")


if __name__ == "__main__":
    main()
