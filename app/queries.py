"""SQL used by the service.

All statements use `?` parameter markers (pyodbc), so user input is never
concatenated into SQL. The reporting queries deliberately stick to ANSI
SQL (COALESCE, CASE, window functions, CTEs) rather than T-SQL-only
syntax (ISNULL, TOP), which keeps them portable - the same text runs on
Oracle, PostgreSQL and SQLite (used in the test suite).

The same report queries live in sql/04_reporting_queries.sql so they can
be run by hand; a test keeps the two copies in sync.
"""

# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------

EMPLOYEE_SELECT = """
SELECT
    e.EmployeeID,
    e.FirstName,
    e.LastName,
    e.DepartmentID,
    d.DepartmentName,
    e.Salary,
    e.Bonus,
    e.HireDate{extra_columns}
FROM dbo.Employee AS e
LEFT JOIN dbo.Department AS d
       ON d.DepartmentID = e.DepartmentID
"""

# Optional Part C rule, computed at read time. The rate is a parameter.
DEFAULT_BONUS_COLUMNS = """,
    CAST(ROUND(COALESCE(e.Bonus, e.Salary * ?), 2) AS DECIMAL(12,2)) AS EffectiveBonus,
    CASE WHEN e.Bonus IS NULL THEN 1 ELSE 0 END AS IsDefaultBonus"""

# OUTPUT INSERTED returns the new identity in the same round trip
# (safer than @@IDENTITY, which can be skewed by triggers).
INSERT_EMPLOYEE = """
INSERT INTO dbo.Employee (FirstName, LastName, DepartmentID, Salary, Bonus, HireDate)
OUTPUT INSERTED.EmployeeID
VALUES (?, ?, ?, ?, ?, ?);
"""

DELETE_EMPLOYEE = "DELETE FROM dbo.Employee WHERE EmployeeID = ?;"

HEALTH_CHECK = "SELECT 1;"

# --------------------------------------------------------------------------
# Part B - compensation reports
# --------------------------------------------------------------------------

# B.1  SUM already skips NULLs; the inner COALESCE makes "NULL = 0" explicit.
#      The outer COALESCE matters: SUM over zero rows is NULL, not 0.
REPORT_TOTAL_BONUS = """
SELECT
    COALESCE(SUM(COALESCE(e.Bonus, 0)), 0) AS TotalBonus,
    COUNT(*)                               AS EmployeeCount,
    COUNT(e.Bonus)                         AS EmployeesWithBonus
FROM dbo.Employee AS e;
"""

# B.2  "= NULL" never matches anything; IS NULL is required.
REPORT_EMPLOYEES_WITHOUT_BONUS = """
SELECT
    e.EmployeeID,
    e.FirstName,
    e.LastName,
    d.DepartmentName,
    e.Salary
FROM dbo.Employee AS e
LEFT JOIN dbo.Department AS d
       ON d.DepartmentID = e.DepartmentID
WHERE e.Bonus IS NULL
ORDER BY e.EmployeeID;
"""

# B.3  100.0 forces decimal arithmetic (no integer division);
#      NULLIF guards against a zero salary even though a CHECK forbids it.
REPORT_BONUS_PERCENTAGE = """
SELECT
    e.EmployeeID,
    e.FirstName,
    e.LastName,
    e.Salary,
    e.Bonus,
    CAST(ROUND(e.Bonus * 100.0 / NULLIF(e.Salary, 0), 2) AS DECIMAL(9,2)) AS BonusPercentOfSalary
FROM dbo.Employee AS e
WHERE e.Bonus IS NOT NULL
ORDER BY BonusPercentOfSalary DESC, e.EmployeeID;
"""

# B.4  Aggregate comparison => HAVING, not WHERE. AVG(Salary) is over every
#      employee in the department, including those without a bonus.
#      INNER JOIN: a department with no staff has no average salary.
REPORT_DEPARTMENTS_BONUS_OVER_AVG_SALARY = """
SELECT
    d.DepartmentID,
    d.DepartmentName,
    COUNT(*)                                AS EmployeeCount,
    SUM(COALESCE(e.Bonus, 0))               AS TotalBonus,
    CAST(AVG(e.Salary) AS DECIMAL(12,2))    AS AverageSalary
FROM dbo.Department AS d
INNER JOIN dbo.Employee AS e
        ON e.DepartmentID = d.DepartmentID
GROUP BY d.DepartmentID, d.DepartmentName
HAVING SUM(COALESCE(e.Bonus, 0)) > AVG(e.Salary)
ORDER BY d.DepartmentID;
"""

# B.5  NULL ordering differs by engine (SQL Server: NULLs last in DESC;
#      Oracle: NULLs FIRST in DESC). The CASE makes "no bonus = last"
#      explicit and portable. RANK() gives ties the same rank (1,2,2,4),
#      so every no-bonus employee shares the last rank.
REPORT_BONUS_RANKING = """
SELECT
    RANK() OVER (
        ORDER BY CASE WHEN e.Bonus IS NULL THEN 1 ELSE 0 END,
                 e.Bonus DESC
    ) AS BonusRank,
    e.EmployeeID,
    e.FirstName,
    e.LastName,
    d.DepartmentName,
    e.Bonus
FROM dbo.Employee AS e
LEFT JOIN dbo.Department AS d
       ON d.DepartmentID = e.DepartmentID
ORDER BY BonusRank, e.EmployeeID;
"""

# B.6  Salary + NULL = NULL, so total compensation must COALESCE the bonus.
#      RANK() = 1 (not TOP 1) returns every employee on a tie.
#      One pass returns both groups; the API splits them.
REPORT_HIGHEST_SALARY = """
WITH Compensation AS (
    SELECT
        e.EmployeeID,
        e.FirstName,
        e.LastName,
        e.Salary,
        e.Bonus,
        e.Salary + COALESCE(e.Bonus, 0) AS TotalCompensation
    FROM dbo.Employee AS e
),
Ranked AS (
    SELECT
        c.*,
        RANK() OVER (ORDER BY c.Salary DESC)            AS SalaryRank,
        RANK() OVER (ORDER BY c.TotalCompensation DESC) AS CompensationRank
    FROM Compensation AS c
)
SELECT
    r.EmployeeID,
    r.FirstName,
    r.LastName,
    r.Salary,
    r.Bonus,
    r.TotalCompensation,
    r.SalaryRank,
    r.CompensationRank
FROM Ranked AS r
WHERE r.SalaryRank = 1
   OR r.CompensationRank = 1
ORDER BY r.EmployeeID;
"""

REPORT_QUERIES = {
    "total-bonus": REPORT_TOTAL_BONUS,
    "employees-without-bonus": REPORT_EMPLOYEES_WITHOUT_BONUS,
    "bonus-percentage": REPORT_BONUS_PERCENTAGE,
    "departments-bonus-over-average-salary": REPORT_DEPARTMENTS_BONUS_OVER_AVG_SALARY,
    "bonus-ranking": REPORT_BONUS_RANKING,
    "highest-salary": REPORT_HIGHEST_SALARY,
}
