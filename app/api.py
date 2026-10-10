"""HTTP handlers.

Each handler: parse + validate input -> call the repository -> shape the
response. The @api_handler decorator turns every error into a consistent
JSON body with the right status code:

    400 validation_error   bad JSON, bad field, unknown department
    404 not_found          employee id does not exist
    409 conflict           other constraint violations
    500 internal_error     anything unexpected (details logged, not returned)
    503 service_unavailable database unreachable / waking up
"""

import functools
import json
import logging
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

import azure.functions as func

from .errors import ApiError, NotFoundError
from .validation import (
    parse_bool,
    parse_json_body,
    parse_positive_int,
    validate_full_employee,
    validate_partial_employee,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Response helpers
# --------------------------------------------------------------------------

def _json_default(value):
    if isinstance(value, Decimal):
        # DECIMAL(12,2) values are exactly representable for display purposes.
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def json_response(payload, status_code: int = 200, headers: dict | None = None) -> func.HttpResponse:
    return func.HttpResponse(
        body=json.dumps(payload, default=_json_default),
        status_code=status_code,
        mimetype="application/json",
        headers=headers,
    )


def _error_response(error: ApiError, request_id: str) -> func.HttpResponse:
    body = {"error": {"code": error.code, "message": error.message, "requestId": request_id}}
    if error.details:
        body["error"]["details"] = error.details
    headers = {"Retry-After": "30"} if error.status_code == 503 else None
    return json_response(body, error.status_code, headers)


def _debug_errors_enabled() -> bool:
    """Troubleshooting switch, off by default: app setting DEBUG_ERRORS=true.

    Puts the underlying exception text in 5xx responses so a deployment can be
    diagnosed without log access. Never leave it on in production.
    """
    return os.environ.get("DEBUG_ERRORS", "").strip().lower() == "true"


def _debug_details(exc: BaseException) -> dict:
    cause = exc.__cause__ or exc
    details = {"debugCause": f"{type(cause).__name__}: {cause}"[:1500]}
    try:
        import pyodbc

        details["debugOdbcDrivers"] = pyodbc.drivers()
    except Exception as import_error:  # pyodbc itself missing is useful to know
        details["debugOdbcDrivers"] = f"pyodbc unavailable: {import_error}"
    return details


def api_handler(handler: Callable) -> Callable:
    @functools.wraps(handler)
    def wrapper(req: func.HttpRequest, *args, **kwargs) -> func.HttpResponse:
        request_id = str(uuid.uuid4())
        try:
            return handler(req, *args, **kwargs)
        except ApiError as error:
            if error.status_code >= 500:
                logger.error("[%s] %s %s failed: %s", request_id, req.method, req.url, error.message)
            original = error
            if error.status_code == 500:
                # Internal detail (e.g. which setting is missing) stays in the logs.
                error = ApiError("An unexpected error occurred.")
            if error.status_code >= 500 and _debug_errors_enabled():
                error.details = {**error.details, **_debug_details(original)}
            return _error_response(error, request_id)
        except Exception as exc:
            logger.exception("[%s] Unhandled error on %s %s", request_id, req.method, req.url)
            error = ApiError("An unexpected error occurred.")
            if _debug_errors_enabled():
                error.details = _debug_details(exc)
            return _error_response(error, request_id)

    return wrapper


def _employee_id(req: func.HttpRequest) -> int:
    return parse_positive_int(req.route_params.get("id"), "id")


def _not_found(employee_id: int) -> NotFoundError:
    return NotFoundError(f"Employee {employee_id} was not found.")


# --------------------------------------------------------------------------
# Part A - CRUD
# --------------------------------------------------------------------------

@api_handler
def create_employee(req: func.HttpRequest, services) -> func.HttpResponse:
    employee = validate_full_employee(parse_json_body(req.get_body()))
    created = services.repository().create(employee)
    location = f"/api/employees/{created['employeeId']}"
    return json_response(created, 201, {"Location": location})


@api_handler
def get_employee(req: func.HttpRequest, services) -> func.HttpResponse:
    employee_id = _employee_id(req)
    rate = services.default_bonus_rate() if parse_bool(req.params.get("applyDefaultBonus"), "applyDefaultBonus") else None
    employee = services.repository().get(employee_id, default_bonus_rate=rate)
    if employee is None:
        raise _not_found(employee_id)
    return json_response(employee)


@api_handler
def list_employees(req: func.HttpRequest, services) -> func.HttpResponse:
    raw_department = req.params.get("departmentId")
    department_id = parse_positive_int(raw_department, "departmentId") if raw_department is not None else None
    rate = services.default_bonus_rate() if parse_bool(req.params.get("applyDefaultBonus"), "applyDefaultBonus") else None
    employees = services.repository().list_employees(department_id=department_id, default_bonus_rate=rate)
    return json_response({"count": len(employees), "items": employees})


@api_handler
def update_employee(req: func.HttpRequest, services) -> func.HttpResponse:
    employee_id = _employee_id(req)
    body = parse_json_body(req.get_body())
    # PUT replaces the whole record; PATCH changes only the fields sent.
    changes = validate_full_employee(body) if req.method.upper() == "PUT" else validate_partial_employee(body)
    updated = services.repository().update(employee_id, changes)
    if updated is None:
        raise _not_found(employee_id)
    return json_response(updated)


@api_handler
def delete_employee(req: func.HttpRequest, services) -> func.HttpResponse:
    employee_id = _employee_id(req)
    if not services.repository().delete(employee_id):
        raise _not_found(employee_id)
    return func.HttpResponse(status_code=204)


# --------------------------------------------------------------------------
# Part B - reports
# --------------------------------------------------------------------------

def _list_payload(items: list) -> dict:
    return {"count": len(items), "items": items}


@api_handler
def report_total_bonus(req: func.HttpRequest, services) -> func.HttpResponse:
    return json_response(services.repository().total_bonus())


@api_handler
def report_employees_without_bonus(req: func.HttpRequest, services) -> func.HttpResponse:
    return json_response(_list_payload(services.repository().employees_without_bonus()))


@api_handler
def report_bonus_percentage(req: func.HttpRequest, services) -> func.HttpResponse:
    return json_response(_list_payload(services.repository().bonus_percentage()))


@api_handler
def report_departments_bonus_over_average_salary(req: func.HttpRequest, services) -> func.HttpResponse:
    return json_response(_list_payload(services.repository().departments_bonus_over_average_salary()))


@api_handler
def report_bonus_ranking(req: func.HttpRequest, services) -> func.HttpResponse:
    return json_response(_list_payload(services.repository().bonus_ranking()))


@api_handler
def report_highest_salary(req: func.HttpRequest, services) -> func.HttpResponse:
    return json_response(services.repository().highest_salary())


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

@api_handler
def health(req: func.HttpRequest, services) -> func.HttpResponse:
    services.repository().ping()
    return json_response({"status": "healthy"})