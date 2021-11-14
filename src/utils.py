import json
import os

ENV_TO_CONFIG_MAP = {
    "PLAID_ACCESS_TOKEN": "access_token",
    "PLAID_ITEM_ID": "item_id",
    "PLAID_CLIENT_ID": "client_id",
    "PLAID_SECRET": "secret",
    "GOOGLE_BUDGET_SPREADSHEET_ID": "budget_spreadsheet_id",
}


def get_config() -> dict:
    """Returns the Config based on the default Config path"""
    with open('config.json') as config_file:
        config = json.load(config_file)

    for env_var_name, config_key in ENV_TO_CONFIG_MAP.items():
        if env_var_name in os.environ:
            config[config_key] = os.environ[env_var_name]

    return config
