/* =====================================================================
   02_seed_data.sql
   Sample data chosen so every reporting endpoint has something to show:

   - 3 employees with NULL bonus            -> "never received a bonus"
   - 3 employees tied on a 5,000 bonus      -> shows RANK() tie handling
   - Sales: total bonus (60,000) > average salary (55,000)
                                            -> the only department returned
   - Aarav has the highest salary (150,000) but Emily has the highest
     total compensation (140,000 + 30,000)  -> answer to Part B.6 is "No"
   - Legal has no employees                 -> empty department edge case
   - HR has a NULL Location                 -> nullable column in action

   Expected totals: company bonus = 115,500.00
   ===================================================================== */

SET NOCOUNT ON;

INSERT INTO dbo.Department (DepartmentID, DepartmentName, Location) VALUES
    (1, 'Engineering', 'London'),
    (2, 'Sales',       'Manchester'),
    (3, 'Finance',     'Edinburgh'),
    (4, 'HR',          NULL),
    (5, 'Legal',       'London');

INSERT INTO dbo.Employee (FirstName, LastName, DepartmentID, Salary, Bonus, HireDate) VALUES
    ('Aarav',  'Shah',    1, 150000.00,  5000.00, '2018-03-12'),
    ('Emily',  'Clarke',  1, 140000.00, 30000.00, '2019-07-01'),
    ('Rohan',  'Mehta',   1,  95000.00,     NULL, '2021-01-18'),
    ('Sophie', 'Turner',  1,  88000.00,  5000.00, '2022-05-09'),
    ('James',  'Wilson',  2,  60000.00, 25000.00, '2020-02-03'),
    ('Priya',  'Nair',    2,  55000.00, 20000.00, '2021-09-27'),
    ('Oliver', 'Brown',   2,  50000.00, 15000.00, '2023-04-17'),
    ('Hannah', 'Patel',   3,  82000.00,  8000.00, '2017-11-06'),
    ('George', 'Evans',   3,  76000.00,     NULL, '2022-10-10'),
    ('Isla',   'Murphy',  3,  70000.00,  5000.00, '2020-06-15'),
    ('Kabir',  'Desai',   4,  48000.00,     NULL, '2024-01-08'),
    ('Chloe',  'Davies',  4,  52000.00,  2500.00, '2023-08-21');
