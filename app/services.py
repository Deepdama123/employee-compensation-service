"""Builds dependencies lazily, once per worker process.

Lazy creation means a missing app setting surfaces as a logged 500 on the
first request (inside the error handler) instead of crashing the host at
import time. Tests swap in their own Services object.
"""

from decimal import Decimal
from functools import cached_property

from .config import Settings, load_settings
from .db import SqlServerDatabase
from .repository import EmployeeRepository


class Services:
    @cached_property
    def settings(self) -> Settings:
        return load_settings()

    @cached_property
    def _repository(self) -> EmployeeRepository:
        return EmployeeRepository(SqlServerDatabase(self.settings.sql_connection_string))

    def repository(self) -> EmployeeRepository:
        return self._repository

    def default_bonus_rate(self) -> Decimal:
        return self.settings.default_bonus_rate


services = Services()
