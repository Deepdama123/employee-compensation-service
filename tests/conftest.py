"""Test fixtures.

The real service targets Azure SQL. For fast, offline tests we run the
*same* repository code and the *same* report SQL against an in-memory
SQLite database:
  - the report queries are ANSI SQL, so they run unchanged;
  - "dbo" is an attached in-memory schema, so dbo.Employee resolves;
  - only the INSERT differs (T-SQL OUTPUT INSERTED -> SQLite RETURNING);
  - the seed rows are read straight from sql/02_seed_data.sql.
"""

import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repository import EmployeeRepository  # noqa: E402

sqlite3.register_adapter(Decimal, str)
sqlite3.register_adapter(date, date.isoformat)

SQLITE_SCHEMA = """
CREATE TABLE dbo.Department (
    DepartmentID   INTEGER PRIMARY KEY,
    DepartmentName TEXT NOT NULL UNIQUE,
    Location       TEXT
);
CREATE TABLE dbo.Employee (
    EmployeeID   INTEGER PRIMARY KEY AUTOINCREMENT,
    FirstName    TEXT NOT NULL,
    LastName     TEXT NOT NULL,
    DepartmentID INTEGER REFERENCES Department (DepartmentID),
    Salary       NUMERIC NOT NULL CHECK (Salary > 0),
    Bonus        NUMERIC CHECK (Bonus IS NULL OR Bonus >= 0),
    HireDate     TEXT
);
"""


def seed_statements() -> list[str]:
    text = (ROOT / "sql" / "02_seed_data.sql").read_text()
    statements = []
    for chunk in text.split(";"):
        start = chunk.find("INSERT INTO")
        if start != -1:
            statements.append(chunk[start:])
    return statements


class SqliteDatabase:
    driver = sqlite3

    def __init__(self):
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("ATTACH DATABASE ':memory:' AS dbo")
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(SQLITE_SCHEMA)

    @contextmanager
    def transaction(self):
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise


class SqliteEmployeeRepository(EmployeeRepository):
    insert_sql = re.sub(
        r"OUTPUT INSERTED\.EmployeeID\s*VALUES \(\?, \?, \?, \?, \?, \?\);",
        "VALUES (?, ?, ?, ?, ?, ?) RETURNING EmployeeID;",
        EmployeeRepository.insert_sql,
    )


@pytest.fixture
def empty_repo():
    return SqliteEmployeeRepository(SqliteDatabase())


@pytest.fixture
def repo(empty_repo):
    connection = empty_repo._db.connection
    for statement in seed_statements():
        connection.execute(statement)
    connection.commit()
    return empty_repo


class FakeServices:
    def __init__(self, repository, rate=Decimal("0.05")):
        self._repository = repository
        self._rate = rate

    def repository(self):
        return self._repository

    def default_bonus_rate(self):
        return self._rate


@pytest.fixture
def services(repo):
    return FakeServices(repo)
