/* =====================================================================
   03_views.sql  (Part C - optional default bonus)

   Decision: the 5% default bonus is CALCULATED AT READ TIME,
   never written into dbo.Employee.Bonus.

   Why:
   - Bonus IS NULL means "no bonus was awarded". Writing 5% into the
     column would destroy that fact, and Part B.2 ("never received a
     bonus") and B.5 (NULLs ranked last) would silently start lying.
   - The rule is a policy. If HR changes it to 7%, a read-time rule
     changes in one place; a write-time rule needs a backfill and leaves
     no record of which values were real awards and which were defaults.
   - Rows inserted after a one-off UPDATE would still be NULL, so a
     write-time approach would also need a trigger or a scheduled job.

   The API applies the same rule via ?applyDefaultBonus=true, with the
   rate taken from the DEFAULT_BONUS_RATE app setting. This view exists
   for analysts and BI tools (e.g. Power BI) that read the database
   directly with read-only credentials.
   ===================================================================== */

CREATE OR ALTER VIEW dbo.vw_EmployeeCompensation
AS
SELECT
    e.EmployeeID,
    e.FirstName,
    e.LastName,
    e.DepartmentID,
    d.DepartmentName,
    e.Salary,
    e.Bonus                                                    AS AwardedBonus,
    CAST(COALESCE(e.Bonus, e.Salary * 0.05) AS DECIMAL(12,2))  AS EffectiveBonus,
    CAST(CASE WHEN e.Bonus IS NULL THEN 1 ELSE 0 END AS BIT)   AS IsDefaultBonus,
    CAST(e.Salary + COALESCE(e.Bonus, e.Salary * 0.05)
         AS DECIMAL(13,2))                                     AS TotalCompensation,
    e.HireDate
FROM dbo.Employee AS e
LEFT JOIN dbo.Department AS d
       ON d.DepartmentID = e.DepartmentID;
