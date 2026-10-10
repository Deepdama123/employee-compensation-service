/* =====================================================================
   04_reporting_queries.sql
   Part B reporting queries - identical to app/queries.py (a unit test
   keeps them in sync). Run any block on its own in the Query editor.
   ===================================================================== */

-- ---------------------------------------------------------------------
-- B.1  Total bonus paid across the company (NULL bonus counts as 0)
-- Endpoint: GET /api/reports/total-bonus
-- ---------------------------------------------------------------------
SELECT
    COALESCE(SUM(COALESCE(e.Bonus, 0)), 0) AS TotalBonus,
    COUNT(*)                               AS EmployeeCount,
    COUNT(e.Bonus)                         AS EmployeesWithBonus
FROM dbo.Employee AS e;

-- ---------------------------------------------------------------------
-- B.2  Employees who have never received a bonus
-- Endpoint: GET /api/reports/employees-without-bonus
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- B.3  Bonus as a percentage of salary (2 dp), bonus holders only
-- Endpoint: GET /api/reports/bonus-percentage
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- B.4  Departments where total bonus > average salary
-- Endpoint: GET /api/reports/departments-bonus-over-average-salary
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- B.5  Employees ranked by bonus, no-bonus employees ranked last
-- Endpoint: GET /api/reports/bonus-ranking
-- ---------------------------------------------------------------------
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

-- ---------------------------------------------------------------------
-- B.6  Highest base salary, and whether they also top total compensation
-- Endpoint: GET /api/reports/highest-salary
-- ---------------------------------------------------------------------
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
