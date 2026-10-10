"""Employee Compensation Service - Azure Functions entry point (Python v2 model).

This file only declares routes. Logic lives in app/:
    api.py         HTTP handlers, error -> status code mapping
    validation.py  request validation
    repository.py  all SQL access
    queries.py     SQL text
    db.py          connections, transactions, transient retry
    config.py      settings from environment variables

All routes are under /api and require a function key (?code=... or the
x-functions-key header), except /api/health.
"""

import azure.functions as func

from app import api
from app.services import services

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


# ---------------------------------------------------------------- Part A: CRUD

@app.route(route="employees", methods=["POST"])
def create_employee(req: func.HttpRequest) -> func.HttpResponse:
    return api.create_employee(req, services)


@app.route(route="employees", methods=["GET"])
def list_employees(req: func.HttpRequest) -> func.HttpResponse:
    return api.list_employees(req, services)


@app.route(route="employees/{id:int}", methods=["GET"])
def get_employee(req: func.HttpRequest) -> func.HttpResponse:
    return api.get_employee(req, services)


@app.route(route="employees/{id:int}", methods=["PUT", "PATCH"])
def update_employee(req: func.HttpRequest) -> func.HttpResponse:
    return api.update_employee(req, services)


@app.route(route="employees/{id:int}", methods=["DELETE"])
def delete_employee(req: func.HttpRequest) -> func.HttpResponse:
    return api.delete_employee(req, services)


# ------------------------------------------------------------- Part B: reports

@app.route(route="reports/total-bonus", methods=["GET"])
def report_total_bonus(req: func.HttpRequest) -> func.HttpResponse:
    return api.report_total_bonus(req, services)


@app.route(route="reports/employees-without-bonus", methods=["GET"])
def report_employees_without_bonus(req: func.HttpRequest) -> func.HttpResponse:
    return api.report_employees_without_bonus(req, services)


@app.route(route="reports/bonus-percentage", methods=["GET"])
def report_bonus_percentage(req: func.HttpRequest) -> func.HttpResponse:
    return api.report_bonus_percentage(req, services)


@app.route(route="reports/departments-bonus-over-average-salary", methods=["GET"])
def report_departments_bonus_over_average_salary(req: func.HttpRequest) -> func.HttpResponse:
    return api.report_departments_bonus_over_average_salary(req, services)


@app.route(route="reports/bonus-ranking", methods=["GET"])
def report_bonus_ranking(req: func.HttpRequest) -> func.HttpResponse:
    return api.report_bonus_ranking(req, services)


@app.route(route="reports/highest-salary", methods=["GET"])
def report_highest_salary(req: func.HttpRequest) -> func.HttpResponse:
    return api.report_highest_salary(req, services)


# ---------------------------------------------------------------------- Health

@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return api.health(req, services)
