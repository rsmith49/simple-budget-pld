import json
import os
from datetime import datetime

ENV_TO_CONFIG_MAP = {
    "PLAID_ACCESS_TOKEN": "access_token",
    "PLAID_ITEM_ID": "item_id",
    "PLAID_CLIENT_ID": "client_id",
    "PLAID_SECRET": "secret",
    "SIMPLEFIN_AUTH": "simplefin_auth",
    "GOOGLE_BUDGET_SPREADSHEET_ID": "budget_spreadsheet_id",
}

# Default config used when no config.json exists (e.g. first cloud start).
_DEFAULT_CONFIG = {
    "settings": {
        "use_local_categorization": False,
        "transformations": ["add_month", "add_cat_1", "add_cat_2", "important_cols"],
        "remove_transactions": [],
        "custom_category_map": {},
        "category_renaming_map": {},
    }
}

_config = None


def get_config_path() -> str:
    """Returns the path to config.json.

    In cloud deployments set CONFIG_PATH to the file inside the GCS-mounted
    data directory, e.g. /root/.ry-n-shres-budget-app/config.json.
    Falls back to ./config.json for local development.
    """
    return os.environ.get("CONFIG_PATH", "config.json")


def get_config() -> dict:
    """Returns the loaded config, reading from disk on first call."""
    global _config

    if _config is None:
        config_path = get_config_path()
        try:
            with open(config_path) as config_file:
                _config = json.load(config_file)
        except FileNotFoundError:
            # First-run in cloud: no config.json yet.  Use defaults and let
            # the user create one via the in-app config editor.
            _config = _DEFAULT_CONFIG.copy()

        for env_var_name, config_key in ENV_TO_CONFIG_MAP.items():
            if env_var_name in os.environ:
                _config[config_key] = os.environ[env_var_name]

    return _config


def reload_config() -> None:
    """Clear the in-memory config cache so the next get_config() re-reads disk.

    Call this after saving an updated config.json through the dashboard UI.
    """
    global _config
    _config = None


def iso_to_epoch(date_str: str) -> int:
    return int(datetime.fromisoformat(date_str).timestamp())


def epoch_to_iso(date_epoch: int) -> str:
    return datetime.fromtimestamp(date_epoch).isoformat()
