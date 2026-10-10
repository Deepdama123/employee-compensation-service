"""Request validation.

Validates shape, types and ranges before anything touches the database,
and collects *all* field errors so the client can fix them in one go.
Money is handled as Decimal end to end (the JSON body is parsed with
parse_float=Decimal), so 0.1 + 0.2 style float errors never reach SQL.
"""

import json
import re
from datetime import date
from decimal import Decimal

from .errors import ValidationError

NAME_MAX_LENGTH = 50                      # VARCHAR(50)
MONEY_MAX = Decimal("9999999999.99")      # DECIMAL(12,2)
INT_MAX = 2_147_483_647                   # SQL INT
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# API field name -> database column. Doubles as the whitelist of columns
# that can ever appear in a dynamic UPDATE statement.
EMPLOYEE_FIELDS = {
    "firstName": "FirstName",
    "lastName": "LastName",
    "departmentId": "DepartmentID",
    "salary": "Salary",
    "bonus": "Bonus",
    "hireDate": "HireDate",
}
REQUIRED_FIELDS = ("firstName", "lastName", "salary")

_MISSING = object()


def _reject_constant(name):
    raise ValueError(f"{name} is not a valid JSON number")


def parse_json_body(raw: bytes) -> dict:
    if not raw:
        raise ValidationError("Request body is required.")
    try:
        body = json.loads(raw, parse_float=Decimal, parse_constant=_reject_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Request body must be valid JSON.") from exc
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object.")
    return body


# --------------------------------------------------------------------------
# Field validators: return the cleaned value or record an error.
# --------------------------------------------------------------------------

def _name(value, field, errors):
    if not isinstance(value, str) or not value.strip():
        errors[field] = "must be a non-empty string"
        return None
    value = value.strip()
    if len(value) > NAME_MAX_LENGTH:
        errors[field] = f"must be at most {NAME_MAX_LENGTH} characters"
        return None
    return value


def _money(value, field, errors, *, nullable, strictly_positive):
    if value is None:
        if not nullable:
            errors[field] = "is required"
        return None
    # bool is a subclass of int in Python - reject true/false explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        errors[field] = "must be a number"
        return None
    amount = Decimal(value)
    if strictly_positive and amount <= 0:
        errors[field] = "must be greater than 0"
    elif amount < 0:
        errors[field] = "must not be negative"
    elif amount > MONEY_MAX:
        errors[field] = f"must not exceed {MONEY_MAX}"
    elif amount.as_tuple().exponent < -2:
        errors[field] = "must have at most 2 decimal places"
    else:
        return amount.quantize(Decimal("0.01"))
    return None


def _department_id(value, field, errors):
    if value is None:
        return None  # nullable in the spec
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= INT_MAX:
        errors[field] = "must be a positive integer"
        return None
    return value


def _hire_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str) or not DATE_PATTERN.match(value):
        errors[field] = "must be a date in YYYY-MM-DD format"
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors[field] = "is not a valid calendar date"
        return None
    if parsed.year < 1900:
        errors[field] = "must be on or after 1900-01-01"
        return None
    return parsed


def _validate_field(field, value, errors):
    if field in ("firstName", "lastName"):
        if value is None:
            errors[field] = "is required"
            return None
        return _name(value, field, errors)
    if field == "salary":
        return _money(value, field, errors, nullable=False, strictly_positive=True)
    if field == "bonus":
        return _money(value, field, errors, nullable=True, strictly_positive=False)
    if field == "departmentId":
        return _department_id(value, field, errors)
    if field == "hireDate":
        return _hire_date(value, field, errors)
    raise AssertionError(field)


def _reject_unknown_fields(body, errors):
    for field in body:
        if field not in EMPLOYEE_FIELDS:
            errors[field] = "is not a recognised field"


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def validate_full_employee(body: dict) -> dict:
    """POST and PUT: the complete employee. Optional fields default to NULL."""
    errors: dict[str, str] = {}
    _reject_unknown_fields(body, errors)
    cleaned = {}
    for field in EMPLOYEE_FIELDS:
        value = body.get(field, _MISSING)
        if value is _MISSING:
            if field in REQUIRED_FIELDS:
                errors[field] = "is required"
                continue
            value = None
        cleaned[field] = _validate_field(field, value, errors)
    if errors:
        raise ValidationError("One or more fields are invalid.", errors)
    return cleaned


def validate_partial_employee(body: dict) -> dict:
    """PATCH: only the fields supplied are changed.

    A field that is absent is left alone; a field sent as null is cleared
    (e.g. {"bonus": null} removes a bonus). Required columns cannot be null.
    """
    errors: dict[str, str] = {}
    _reject_unknown_fields(body, errors)
    if not body:
        raise ValidationError("Provide at least one field to update.")
    cleaned = {}
    for field, value in body.items():
        if field in EMPLOYEE_FIELDS:
            cleaned[field] = _validate_field(field, value, errors)
    if errors:
        raise ValidationError("One or more fields are invalid.", errors)
    return cleaned


def parse_positive_int(raw: str | None, name: str) -> int:
    if raw is None or not re.fullmatch(r"[0-9]{1,10}", raw) or not 1 <= int(raw) <= INT_MAX:
        raise ValidationError(f"'{name}' must be a positive integer.", {name: "must be a positive integer"})
    return int(raw)


def parse_bool(raw: str | None, name: str) -> bool:
    if raw is None or raw == "":
        return False
    value = raw.strip().lower()
    if value in ("true", "1", "yes"):
        return True
    if value in ("false", "0", "no"):
        return False
    raise ValidationError(f"'{name}' must be true or false.", {name: "must be true or false"})
