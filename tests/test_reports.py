"""Part B report queries, run against the seed data from sql/02_seed_data.sql."""

import re
from pathlib import Path

import pytest

from app import queries

ROOT = Path(__file__).resolve().parents[1]


def names(rows):
    return [f"{r['firstName']} {r['lastName']}" for r in rows]


def test_b1_total_bonus_treats_null_as_zero(repo):
    result = repo.total_bonus()
    assert result["totalBonus"] == pytest.approx(115500.00)
    assert result["employeeCount"] == 12
    assert result["employeesWithBonus"] == 9


def test_b1_total_bonus_is_zero_not_null_on_empty_table(empty_repo):
    assert empty_repo.total_bonus()["totalBonus"] == 0


def test_b2_employees_without_bonus(repo):
    assert names(repo.employees_without_bonus()) == ["Rohan Mehta", "George Evans", "Kabir Desai"]


def test_b3_bonus_percentage_rounded_and_excludes_nulls(repo):
    rows = {r["employeeId"]: float(r["bonusPercentOfSalary"]) for r in repo.bonus_percentage()}
    assert len(rows) == 9
    assert rows[1] == 3.33     # 5,000 / 150,000
    assert rows[2] == 21.43    # 30,000 / 140,000
    assert rows[5] == 41.67    # 25,000 / 60,000
    assert rows[7] == 30.00
    assert 3 not in rows       # Rohan has no bonus


def test_b4_departments_where_total_bonus_exceeds_average_salary(repo):
    rows = repo.departments_bonus_over_average_salary()
    assert [r["departmentName"] for r in rows] == ["Sales"]
    sales = rows[0]
    assert sales["totalBonus"] == pytest.approx(60000)
    assert sales["averageSalary"] == pytest.approx(55000)
    assert sales["employeeCount"] == 3


def test_b5_ranking_puts_no_bonus_last_and_shares_ties(repo):
    rows = repo.bonus_ranking()
    assert len(rows) == 12                                  # nobody excluded
    ranks = [(r["firstName"], r["bonusRank"]) for r in rows]
    assert ranks[0] == ("Emily", 1)
    tied = {name for name, rank in ranks if rank == 6}
    assert tied == {"Aarav", "Sophie", "Isla"}              # 5,000 each
    assert ("Chloe", 9) in ranks                            # RANK skips 7, 8
    last = [r for r in rows if r["bonus"] is None]
    assert {r["bonusRank"] for r in last} == {10}
    assert rows[-3:] == last                                # NULLs at the bottom


def test_b6_highest_salary_and_total_compensation(repo):
    result = repo.highest_salary()
    assert names(result["highestSalaryEmployees"]) == ["Aarav Shah"]
    assert names(result["highestTotalCompensationEmployees"]) == ["Emily Clarke"]
    assert result["highestTotalCompensationEmployees"][0]["totalCompensation"] == pytest.approx(170000)
    assert result["highestSalaryEmployeeAlsoHasHighestTotalCompensation"] is False


def test_b6_total_compensation_counts_null_bonus_as_zero(repo):
    # Give a no-bonus employee the top salary: Salary + NULL must not become NULL.
    repo.update(3, {"salary": 200000})
    result = repo.highest_salary()
    top = result["highestSalaryEmployees"][0]
    assert top["firstName"] == "Rohan"
    assert top["totalCompensation"] == pytest.approx(200000)
    assert result["highestSalaryEmployeeAlsoHasHighestTotalCompensation"] is True


def test_b6_ties_return_every_employee(repo):
    repo.update(2, {"salary": 150000})                      # Emily ties Aarav
    result = repo.highest_salary()
    assert names(result["highestSalaryEmployees"]) == ["Aarav Shah", "Emily Clarke"]
    assert result["highestSalaryEmployeeAlsoHasHighestTotalCompensation"] is True


def test_sql_script_matches_application_queries():
    """sql/04_reporting_queries.sql must stay identical to app/queries.py."""
    script = re.sub(r"\s+", " ", (ROOT / "sql" / "04_reporting_queries.sql").read_text())
    for name, sql in queries.REPORT_QUERIES.items():
        assert re.sub(r"\s+", " ", sql).strip() in script, name
