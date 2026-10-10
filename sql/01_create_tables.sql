/* =====================================================================
   01_create_tables.sql
   Employee Compensation Service - schema (Azure SQL Database / SQL Server)

   Safe to re-run: drops and recreates both tables.
   No GO separators, so it runs as-is in the Azure portal Query editor.
   Run order: 01_create_tables.sql -> 02_seed_data.sql -> 03_views.sql
   ===================================================================== */

SET NOCOUNT ON;

-- Drop child first because of the foreign key.
IF OBJECT_ID(N'dbo.Employee', N'U') IS NOT NULL
    DROP TABLE dbo.Employee;

IF OBJECT_ID(N'dbo.Department', N'U') IS NOT NULL
    DROP TABLE dbo.Department;

CREATE TABLE dbo.Department
(
    DepartmentID    INT           NOT NULL,
    DepartmentName  VARCHAR(100)  NOT NULL,
    Location        VARCHAR(100)  NULL,

    CONSTRAINT PK_Department PRIMARY KEY (DepartmentID),
    CONSTRAINT UQ_Department_Name UNIQUE (DepartmentName)
);

CREATE TABLE dbo.Employee
(
    EmployeeID    INT            IDENTITY(1,1) NOT NULL,
    FirstName     VARCHAR(50)    NOT NULL,
    LastName      VARCHAR(50)    NOT NULL,
    DepartmentID  INT            NULL,      -- spec does not mark it NOT NULL
    Salary        DECIMAL(12,2)  NOT NULL,
    Bonus         DECIMAL(12,2)  NULL,      -- NULL = no bonus awarded
    HireDate      DATE           NULL,

    CONSTRAINT PK_Employee PRIMARY KEY (EmployeeID),
    CONSTRAINT FK_Employee_Department
        FOREIGN KEY (DepartmentID) REFERENCES dbo.Department (DepartmentID),

    -- Defence in depth: the API validates these too, but the database
    -- is the last line of defence against bad data from any source.
    CONSTRAINT CK_Employee_Salary_Positive CHECK (Salary > 0),
    CONSTRAINT CK_Employee_Bonus_NonNegative CHECK (Bonus IS NULL OR Bonus >= 0)
);

-- SQL Server does NOT index foreign keys automatically.
-- This index supports "list employees by department" and the
-- per-department reporting query (GROUP BY DepartmentID).
CREATE INDEX IX_Employee_DepartmentID
    ON dbo.Employee (DepartmentID)
    INCLUDE (Salary, Bonus);
