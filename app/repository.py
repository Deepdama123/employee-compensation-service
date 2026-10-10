"""Data access for employees and reports.

The only module that talks SQL. It returns plain dicts with camelCase
keys, so the HTTP layer never sees cursors, rows or column names.
"""

import logging
from decimal import Decimal

from . import queries
from .errors import ConflictError, ServiceUnavailableError, ValidationError
from .validation import EMPLOYEE_FIELDS

logger = logging.getLogger(__name__)

_COLUMN_LIST = ", ".join(EMPLOYEE_FIELDS.values())  # FirstName, LastName, ...


def _camel(column: str) -> str:
    """EmployeeID -> employeeId, IsDefaultBonus -> isDefaultBonus."""
    name = column[0].lower() + column[1:]
    return name[:-2] + "Id" if name.endswith("ID") else name


def _rows(cursor) -> list[dict]:
    columns = [_camel(col[0]) for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


class EmployeeRepository:
    insert_sql = queries.INSERT_EMPLOYEE  # overridable for other SQL dialects

    def __init__(self, database):
        self._db = database

    # ------------------------------------------------------------------
    # Error translation: driver exceptions -> API errors
    # ------------------------------------------------------------------

    def _run(self, work):
        driver = self._db.driver
        try:
            with self._db.transaction() as connection:
                return work(connection.cursor())
        except driver.IntegrityError as exc:
            message = str(exc)
            if "FOREIGN KEY" in message.upper():
                raise ValidationError(
                    "The referenced department does not exist.",
                    {"departmentId": "no department with this id"},
                ) from exc
            logger.warning("Integrity error: %s", message)
            raise ConflictError("The request conflicts with existing data.") from exc
        except driver.OperationalError as exc:
            logger.exception("Database operational error")
            raise ServiceUnavailableError("The database is temporarily unavailable. Please retry shortly.") from exc

    # ------------------------------------------------------------------
    # Part A - CRUD
    # ------------------------------------------------------------------

    def _select(self, cursor, where: str = "", params: tuple = (), default_bonus_rate: Decimal | None = None):
        extra = queries.DEFAULT_BONUS_COLUMNS if default_bonus_rate is not None else ""
        sql = queries.EMPLOYEE_SELECT.format(extra_columns=extra) + where
        all_params = ((default_bonus_rate,) if default_bonus_rate is not None else ()) + params
        cursor.execute(sql, all_params)
        rows = _rows(cursor)
        for row in rows:
            if "isDefaultBonus" in row:
                row["isDefaultBonus"] = bool(row["isDefaultBonus"])
        return rows

    def _get(self, cursor, employee_id: int, default_bonus_rate=None):
        rows = self._select(cursor, "WHERE e.EmployeeID = ?;", (employee_id,), default_bonus_rate)
        return rows[0] if rows else None

    def create(self, employee: dict) -> dict:
        def work(cursor):
            cursor.execute(self.insert_sql, tuple(employee[f] for f in EMPLOYEE_FIELDS))
            new_id = cursor.fetchone()[0]
            return self._get(cursor, new_id)

        return self._run(work)

    def get(self, employee_id: int, default_bonus_rate: Decimal | None = None) -> dict | None:
        return self._run(lambda cursor: self._get(cursor, employee_id, default_bonus_rate))

    def list_employees(self, department_id: int | None = None, default_bonus_rate: Decimal | None = None) -> list[dict]:
        if department_id is None:
            where, params = "ORDER BY e.EmployeeID;", ()
        else:
            where, params = "WHERE e.DepartmentID = ? ORDER BY e.EmployeeID;", (department_id,)
        return self._run(lambda cursor: self._select(cursor, where, params, default_bonus_rate))

    def update(self, employee_id: int, changes: dict) -> dict | None:
        # Column names come from the EMPLOYEE_FIELDS whitelist, never from
        # the request; values are always bound parameters.
        assignments = ", ".join(f"{EMPLOYEE_FIELDS[field]} = ?" for field in changes)
        sql = f"UPDATE dbo.Employee SET {assignments} WHERE EmployeeID = ?;"

        def work(cursor):
            cursor.execute(sql, (*changes.values(), employee_id))
            if cursor.rowcount == 0:
                return None
            return self._get(cursor, employee_id)

        return self._run(work)

    def delete(self, employee_id: int) -> bool:
        def work(cursor):
            cursor.execute(queries.DELETE_EMPLOYEE, (employee_id,))
            return cursor.rowcount > 0

        return self._run(work)

    def ping(self) -> None:
        self._run(lambda cursor: cursor.execute(queries.HEALTH_CHECK).fetchone())

    # ------------------------------------------------------------------
    # Part B - reports
    # ------------------------------------------------------------------

    def _report(self, name: str) -> list[dict]:
        def work(cursor):
            cursor.execute(queries.REPORT_QUERIES[name])
            return _rows(cursor)

        return self._run(work)

    def total_bonus(self) -> dict:
        return self._report("total-bonus")[0]

    def employees_without_bonus(self) -> list[dict]:
        return self._report("employees-without-bonus")

    def bonus_percentage(self) -> list[dict]:
        return self._report("bonus-percentage")

    def departments_bonus_over_average_salary(self) -> list[dict]:
        return self._report("departments-bonus-over-average-salary")

    def bonus_ranking(self) -> list[dict]:
        return self._report("bonus-ranking")

    def highest_salary(self) -> dict:
        rows = self._report("highest-salary")
        top_salary = [r for r in rows if r["salaryRank"] == 1]
        top_compensation = [r for r in rows if r["compensationRank"] == 1]
        for row in rows:
            row["hasHighestTotalCompensation"] = row["compensationRank"] == 1
            row.pop("salaryRank")
            row.pop("compensationRank")
        return {
            # A list, because two people can share the highest salary.
            "highestSalaryEmployees": top_salary,
            "highestTotalCompensationEmployees": top_compensation,
            "highestSalaryEmployeeAlsoHasHighestTotalCompensation":
                any(r["hasHighestTotalCompensation"] for r in top_salary),
        }
