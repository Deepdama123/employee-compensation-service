"""Settings come from environment variables only - never from source code.

Locally they are loaded from local.settings.json (git-ignored).
In Azure they are Function App "Environment variables" (app settings),
ideally as Key Vault references:
    @Microsoft.KeyVault(SecretUri=https://<vault>.vault.azure.net/secrets/SqlConnectionString/)
"""

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .errors import ConfigurationError

CONNECTION_STRING_SETTING = "SqlConnectionString"
DEFAULT_BONUS_RATE_SETTING = "DEFAULT_BONUS_RATE"


@dataclass(frozen=True)
class Settings:
    sql_connection_string: str
    default_bonus_rate: Decimal


def load_settings() -> Settings:
    connection_string = os.environ.get(CONNECTION_STRING_SETTING, "").strip()
    if not connection_string:
        raise ConfigurationError(f"App setting '{CONNECTION_STRING_SETTING}' is not configured.")

    raw_rate = os.environ.get(DEFAULT_BONUS_RATE_SETTING, "0.05")
    try:
        rate = Decimal(raw_rate)
    except InvalidOperation as exc:
        raise ConfigurationError(f"App setting '{DEFAULT_BONUS_RATE_SETTING}' must be a number.") from exc
    if not Decimal("0") <= rate <= Decimal("1"):
        raise ConfigurationError(f"App setting '{DEFAULT_BONUS_RATE_SETTING}' must be between 0 and 1.")

    return Settings(sql_connection_string=connection_string, default_bonus_rate=rate)
