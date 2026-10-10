"""HTTP handler tests: status codes, validation, error handling, Part C."""

import json
import sqlite3

import azure.functions as func
import pytest

from app import api
from app.errors import ConfigurationError
from app.services import Services
from conftest import FakeServices


def request(method="GET", url="/api/employees", body=None, params=None, route_params=None):
    raw = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
    return func.HttpRequest(method=method, url=url, body=raw, params=params or {},
                            route_params=route_params or {}, headers={})


def payload(response):
    return json.loads(response.get_body()) if response.get_body() else None


NEW_EMPLOYEE = {"firstName": "Asha", "lastName": "Kapoor", "departmentId": 2,
                "salary": 64000.50, "hireDate": "2025-02-01"}


# ------------------------------------------------------------------ create

def test_create_without_bonus_returns_201_and_location(services):
    response = api.create_employee(request("POST", body=NEW_EMPLOYEE), services)
    body = payload(response)
    assert response.status_code == 201
    assert response.headers["Location"] == f"/api/employees/{body['employeeId']}"
    assert body["bonus"] is None
    assert body["departmentName"] == "Sales"
    assert body["salary"] == 64000.50


def test_create_reports_every_invalid_field(services):
    bad = {"firstName": " ", "salary": -1, "bonus": "lots", "hireDate": "01/02/2025", "age": 30}
    response = api.create_employee(request("POST", body=bad), services)
    error = payload(response)["error"]
    assert response.status_code == 400
    assert set(error["details"]) == {"firstName", "lastName", "salary", "bonus", "hireDate", "age"}


@pytest.mark.parametrize("raw", [b"", b"not json", b"[1, 2]", b'{"salary": NaN}'])
def test_create_rejects_malformed_bodies(services, raw):
    assert api.create_employee(request("POST", body=raw), services).status_code == 400


def test_create_rejects_more_than_two_decimal_places(services):
    response = api.create_employee(request("POST", body={**NEW_EMPLOYEE, "salary": 1000.123}), services)
    assert payload(response)["error"]["details"] == {"salary": "must have at most 2 decimal places"}


def test_create_with_unknown_department_is_400_not_500(services):
    response = api.create_employee(request("POST", body={**NEW_EMPLOYEE, "departmentId": 99}), services)
    assert response.status_code == 400
    assert "departmentId" in payload(response)["error"]["details"]


# -------------------------------------------------------------------- read

def test_get_existing_and_missing(services):
    assert payload(api.get_employee(request(route_params={"id": "2"}), services))["firstName"] == "Emily"
    response = api.get_employee(request(route_params={"id": "999"}), services)
    assert response.status_code == 404
    assert payload(response)["error"]["code"] == "not_found"


def test_list_with_and_without_department_filter(services):
    assert payload(api.list_employees(request(), services))["count"] == 12
    sales = payload(api.list_employees(request(params={"departmentId": "2"}), services))
    assert sales["count"] == 3
    assert {e["departmentName"] for e in sales["items"]} == {"Sales"}


def test_list_rejects_bad_filter(services):
    assert api.list_employees(request(params={"departmentId": "abc"}), services).status_code == 400


# ------------------------------------------------------------------ update

def test_patch_changes_only_bonus(services):
    response = api.update_employee(request("PATCH", body={"bonus": 7500}, route_params={"id": "3"}), services)
    body = payload(response)
    assert response.status_code == 200
    assert body["bonus"] == 7500
    assert body["salary"] == 95000           # untouched


def test_patch_null_clears_bonus(services):
    response = api.update_employee(request("PATCH", body={"bonus": None}, route_params={"id": "1"}), services)
    assert payload(response)["bonus"] is None


def test_patch_cannot_null_required_field(services):
    response = api.update_employee(request("PATCH", body={"salary": None}, route_params={"id": "1"}), services)
    assert response.status_code == 400


def test_put_requires_full_record(services):
    response = api.update_employee(request("PUT", body={"bonus": 1}, route_params={"id": "1"}), services)
    assert response.status_code == 400


def test_update_missing_employee_is_404(services):
    response = api.update_employee(request("PATCH", body={"bonus": 1}, route_params={"id": "999"}), services)
    assert response.status_code == 404


# ------------------------------------------------------------------ delete

def test_delete_then_get_is_404(services):
    assert api.delete_employee(request("DELETE", route_params={"id": "4"}), services).status_code == 204
    assert api.get_employee(request(route_params={"id": "4"}), services).status_code == 404
    assert api.delete_employee(request("DELETE", route_params={"id": "4"}), services).status_code == 404


# ------------------------------------------------------- Part C default bonus

def test_default_bonus_is_computed_on_read_not_stored(services, repo):
    response = api.get_employee(request(route_params={"id": "3"}, params={"applyDefaultBonus": "true"}), services)
    body = payload(response)
    assert body["bonus"] is None                  # stored value untouched
    assert body["effectiveBonus"] == 4750.00      # 5% of 95,000
    assert body["isDefaultBonus"] is True
    assert repo.get(3)["bonus"] is None
    awarded = payload(api.get_employee(request(route_params={"id": "2"}, params={"applyDefaultBonus": "true"}), services))
    assert awarded["effectiveBonus"] == 30000 and awarded["isDefaultBonus"] is False


def test_default_bonus_flag_must_be_boolean(services):
    assert api.list_employees(request(params={"applyDefaultBonus": "maybe"}), services).status_code == 400


# ------------------------------------------------------------- error paths

def test_unexpected_error_returns_500_without_leaking_details(repo):
    class Broken(FakeServices):
        def repository(self):
            raise RuntimeError("password=hunter2 server=prod-sql")

    response = api.get_employee(request(route_params={"id": "1"}), Broken(repo))
    body = payload(response)
    assert response.status_code == 500
    assert "hunter2" not in json.dumps(body)
    assert body["error"]["requestId"]


def test_missing_connection_string_is_logged_500(monkeypatch):
    monkeypatch.delenv("SqlConnectionString", raising=False)
    response = api.get_employee(request(route_params={"id": "1"}), Services())
    assert response.status_code == 500
    assert "SqlConnectionString" not in response.get_body().decode()


def test_database_outage_returns_503_with_retry_after(repo, monkeypatch):
    def down(*_args, **_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(repo, "_select", down)
    response = api.list_employees(request(), FakeServices(repo))
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"


def test_reports_respond_with_json(services):
    for handler in (api.report_total_bonus, api.report_employees_without_bonus, api.report_bonus_percentage,
                    api.report_departments_bonus_over_average_salary, api.report_bonus_ranking,
                    api.report_highest_salary, api.health):
        response = handler(request(), services)
        assert response.status_code == 200, handler.__name__
        assert response.mimetype == "application/json"


def test_config_rejects_invalid_bonus_rate(monkeypatch):
    from app.config import load_settings
    monkeypatch.setenv("SqlConnectionString", "x")
    monkeypatch.setenv("DEFAULT_BONUS_RATE", "five percent")
    with pytest.raises(ConfigurationError):
        load_settings()
