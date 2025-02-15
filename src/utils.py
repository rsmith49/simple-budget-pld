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


_config = None


def get_config() -> dict:
    """Returns the Config based on the default Config path"""
    global _config

    if _config is None:
        with open('config.json') as config_file:
            _config = json.load(config_file)

        for env_var_name, config_key in ENV_TO_CONFIG_MAP.items():
            if env_var_name in os.environ:
                _config[config_key] = os.environ[env_var_name]

    return _config


def iso_to_epoch(date_str: str) -> int:
    return int(datetime.fromisoformat(date_str).timestamp())


def epoch_to_iso(date_epoch: int) -> str:
    return datetime.fromtimestamp(date_epoch).isoformat()
