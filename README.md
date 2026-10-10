# Employee Compensation Service

A small HR backend built as HTTP-triggered **Azure Functions (Python, v2 programming model)** on **Azure SQL Database**. It covers employee CRUD (Part A), six compensation reports (Part B) and production basics: secrets in config, consistent error handling, and an optional default bonus (Part C).

Clients only talk to the Functions. There is no direct database access.

```
Client ──HTTPS + function key──▶ Azure Functions (/api/...)
                                   │
                                   ├─ function_app.py   routes only
                                   ├─ app/api.py        validate → call repo → JSON + status code
                                   ├─ app/validation.py field rules, Decimal money
                                   ├─ app/repository.py the only code that runs SQL
                                   ├─ app/queries.py    parameterised SQL text
                                   ├─ app/db.py         connection, transaction, transient retry
                                   └─ app/config.py     settings from environment variables
                                   │
                                   ▼
                          Azure SQL Database (dbo.Department, dbo.Employee)
```

## Endpoints

All routes sit under `/api` and need a function key (`?code=<key>` or the `x-functions-key` header), apart from `/api/health`.

| Part | Method | Route | Notes |
|---|---|---|---|
| A.1 | POST | `/employees` | `bonus` is optional. Returns **201** and a `Location` header |
| A.2 | GET | `/employees/{id}` | **404** if the employee doesn't exist |
| A.3 | GET | `/employees?departmentId=2` | The filter is optional |
| A.4 | PATCH | `/employees/{id}` | Partial update. `{"bonus": null}` removes a bonus |
| A.4 | PUT | `/employees/{id}` | Full replacement |
| A.5 | DELETE | `/employees/{id}` | Returns **204**, or **404** if not found |
| B.1 | GET | `/reports/total-bonus` | NULL bonus counts as 0 |
| B.2 | GET | `/reports/employees-without-bonus` | `Bonus IS NULL` |
| B.3 | GET | `/reports/bonus-percentage` | Bonus holders only, rounded to 2 dp |
| B.4 | GET | `/reports/departments-bonus-over-average-salary` | `HAVING SUM(bonus) > AVG(salary)` |
| B.5 | GET | `/reports/bonus-ranking` | `RANK()`, with no-bonus employees ranked last |
| B.6 | GET | `/reports/highest-salary` | Top earner(s) and whether they also lead on total compensation |
| C | GET | `/employees/{id}?applyDefaultBonus=true` | Adds `effectiveBonus` and `isDefaultBonus` |
| – | GET | `/health` | Anonymous. Runs `SELECT 1` against the database |

Every error has the same shape:

```json
{ "error": { "code": "validation_error", "message": "One or more fields are invalid.",
             "details": { "salary": "must be greater than 0" }, "requestId": "…" } }
```

| Status | When |
|---|---|
| 400 | Malformed JSON, invalid or unknown field, or a department that doesn't exist |
| 404 | Employee not found |
| 409 | Any other constraint conflict |
| 500 | Unexpected error. The client gets a generic message and the details go to the logs |
| 503 | Database unreachable or waking from auto-pause. Includes `Retry-After` |

## Running it

### 1. Database
Run the scripts in `sql/`, in order, against an Azure SQL Database. The portal's **Query editor** works fine for this.

1. `01_create_tables.sql`: tables, keys, CHECK constraints, and an index on the FK
2. `02_seed_data.sql`: 5 departments and 12 employees, chosen to exercise every report
3. `03_views.sql`: `vw_EmployeeCompensation` (the read-time default bonus, for BI tools)
4. `04_reporting_queries.sql`: the Part B queries on their own, for running by hand

### 2. Local
Prerequisites: Python 3.11, [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local), and [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp local.settings.json.example local.settings.json   # then fill in SqlConnectionString
func start
```

Your client IP must be allowed in the SQL server's firewall. Try the endpoints with `requests.http` (VS Code REST Client) or curl:

```bash
curl http://localhost:7071/api/reports/highest-salary
```

### 3. Tests
```bash
pytest -q
```
34 tests. They run the real repository code and the real report SQL against in-memory SQLite, seeded from `sql/02_seed_data.sql`. The report queries are ANSI SQL, so they run unchanged. Only the `INSERT … OUTPUT INSERTED` is swapped for SQLite's `RETURNING`. A test also keeps `sql/04_reporting_queries.sql` identical to `app/queries.py`.

### 4. Deploy to Azure
```bash
func azure functionapp publish <function-app-name>
```
Then add these app settings to the Function App (**Settings → Environment variables**):

| Setting | Value |
|---|---|
| `SqlConnectionString` | ODBC connection string (or a Key Vault reference) |
| `DEFAULT_BONUS_RATE` | `0.05` (optional, this is the default) |

On the SQL server, turn on **Allow Azure services and resources to access this server**.

## Design decisions

**Secrets.** The connection string is only ever read from an environment variable. `local.settings.json` is git-ignored, and in Azure the value lives in app settings. The next step would be a Key Vault reference, or a managed identity with no password at all (`Authentication=ActiveDirectoryMsi`).

**SQL injection.** Every value is a bound `?` parameter. The PATCH statement is built dynamically, but its column names only ever come from a fixed whitelist (`EMPLOYEE_FIELDS`), never from the request.

**Treating NULL bonuses correctly.** This is the core of Part B:
- `SUM` over zero rows returns NULL, so B.1 wraps it in `COALESCE(…, 0)`.
- `= NULL` matches nothing, so B.2 uses `IS NULL`.
- `Salary + NULL` is NULL, so B.6 uses `Salary + COALESCE(Bonus, 0)`.
- NULL sort order differs between engines (SQL Server puts NULLs last on `DESC`, Oracle puts them first). B.5 therefore uses an explicit `CASE WHEN Bonus IS NULL THEN 1 ELSE 0 END` instead of relying on the default.

**Ties.** B.5 and B.6 use `RANK()` rather than `TOP 1`. If two people share the top salary, both are returned.

**Money.** JSON is parsed with `parse_float=Decimal` and checked against `DECIMAL(12,2)`: no negatives, at most 2 decimal places, and within range. Floats never reach SQL. B.3 multiplies by `100.0` so the division is never integer division.

**Part C default bonus: read time, not write time.** `Bonus IS NULL` means "no bonus was awarded". Writing 5% into the column would destroy that fact and break B.2 and B.5. The rate is also a policy that can change, and computing it on read keeps it in one setting (`DEFAULT_BONUS_RATE`) with no backfill needed. The API returns the stored `bonus` and a separate `effectiveBonus` with an `isDefaultBonus` flag, so nobody mistakes a default for a real award. If the business really did want 5% awarded, the right approach is a one-off audited `UPDATE` signed off by HR, not a silent default.

**Connections.** Each request opens a connection, commits or rolls back, and closes it. ODBC pooling makes this cheap. Transient Azure SQL errors (for example 40613, when a serverless database is resuming) are retried with backoff. If the database is still unavailable, the API returns 503 with `Retry-After`.

**Constraints in the database as well as the API.** There are CHECK constraints on salary and bonus, plus the FK. That way bad data is blocked even if it arrives through some other path. SQL Server doesn't index foreign keys automatically, so `IX_Employee_DepartmentID` supports both the department filter and the B.4 report.

## Assumptions
- `DepartmentID` and `HireDate` are nullable, because the spec doesn't mark them NOT NULL. Employees with no department still appear in the employee reports but not in the department report (B.4).
- "Never received a bonus" means `Bonus IS NULL`. A stored `0` counts as an explicit zero award.
- B.3 includes every employee with a non-NULL bonus.
- Salary must be greater than 0, so bonus-as-percentage-of-salary is always defined. `NULLIF` guards it anyway.
- Departments are reference data, created by the SQL script. The brief only asks for employee CRUD.
- Delete is a hard delete.
- The default bonus applies to employee reads only. The reports answer the questions as asked, against actual awards.

## What I'd add next
- Managed identity for SQL, so there is no password anywhere
- Pagination (`OFFSET … FETCH`) on the employee list
- Soft delete and an audit trail for salary and bonus changes, which matter for HR data
- `NVARCHAR` for names, since `VARCHAR` can mangle non-Latin characters
- CI pipeline (GitHub Actions) that runs the tests and deploys
- Azure API Management in front for auth (Entra ID), rate limiting and an OpenAPI spec
- Integration tests against a real Azure SQL / SQL Server container
