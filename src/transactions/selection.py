"""
Methods for selecting when and how to retrieve new transactions data
"""
import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable

import pandas as pd
from dateutil.relativedelta import relativedelta

from .plaid_transactions import get_transactions_df as get_plaid_transactions_df
from .simplefin_transactions import get_transactions_df as get_sf_transactions_df
from ..utils import get_config

EXISTING_TRANSACTIONS_FILE = f"{Path.home()}/.ry-n-shres-budget-app/all_transactions.csv"
TRANSACTIONS_PULL_INFO_FILE = f"{Path.home()}/.ry-n-shres-budget-app/latest_pull_info.json"
TRANSACTION_GRACE_BUFFER = relativedelta(days=10)  # How far before latest transaction to pull from
TRANSACTIONS_PULL_BUFFER = relativedelta(days=1)  # How long to wait before sending another request since the last one

GetTransactionsFnType = Callable[[str, str], pd.DataFrame]


empty_transaction_df = pd.DataFrame({
    key: []
    # TODO: Move this column definition somewhere central
    for key in ["date", "name", "merchant_name", "category", "payment_channel", "amount"]
})


class TransactionMethod(str, Enum):
    PLAID = "plaid"
    SIMPLE_FIN = "simple_fin"
    NONE = "none"


def get_transactions_wrapper(fn: GetTransactionsFnType, method: TransactionMethod) -> GetTransactionsFnType:
    def wrapped(start_date: str, end_date: str) -> pd.DataFrame:
        print(f"Running {method} for latest transactions...")
        df = fn(start_date, end_date)
        with open(TRANSACTIONS_PULL_INFO_FILE, "w") as info_file:
            json.dump(
                {
                    "latest_pull": datetime.now().isoformat(),
                    "latest_transaction_date": df["date"].astype(str).max(),
                    "method": str(method),
                    "success": True,
                },
                info_file,
                indent=2,
            )

        return df
    return wrapped


METHOD_MAP = {
    TransactionMethod.PLAID: get_plaid_transactions_df,
    TransactionMethod.SIMPLE_FIN: get_sf_transactions_df,
    TransactionMethod.NONE: lambda start_date, end_date: empty_transaction_df.copy(),
}
# Wrapping the retrieval fns
METHOD_MAP = {
    key: get_transactions_wrapper(val, key)
    for key, val in METHOD_MAP.items()
}


def get_transaction_method() -> GetTransactionsFnType:
    config = get_config()
    if config.get("access_token") and config.get("item_id") and config.get("client_id") and config.get("secret"):
        method_name = TransactionMethod.PLAID
    elif config.get("simplefin_auth"):
        method_name = TransactionMethod.SIMPLE_FIN
    else:
        method_name = TransactionMethod.NONE

    return METHOD_MAP[method_name]


def maybe_pull_latest_transactions() -> pd.DataFrame:
    try:
        existing_df = pd.read_csv(EXISTING_TRANSACTIONS_FILE)
        existing_df['date'] = existing_df['date'].astype(str)
    except FileNotFoundError:
        print("No existing transactions found, using only new data")
        existing_df = None

    # Get latest transactions
    now = datetime.now().strftime('%Y-%m-%d')
    get_transactions_df = get_transaction_method()

    # Check if we should exit early
    try:
        with open(TRANSACTIONS_PULL_INFO_FILE) as pull_info_file:
            latest_pull_info = json.load(pull_info_file)
        latest_pull_date = latest_pull_info["latest_pull"]

        if (datetime.now() - TRANSACTIONS_PULL_BUFFER) <= datetime.fromisoformat(latest_pull_date):
            # Return early if the last pull was recent
            return existing_df
    except FileNotFoundError:
        latest_pull_date = None

    # TODO: Add error handling for failed API calls
    if existing_df is not None:
        latest_date = existing_df['date'].max()
        start_date = (datetime.strptime(latest_date, '%Y-%m-%d') - TRANSACTION_GRACE_BUFFER).strftime('%Y-%m-%d')
        latest_transactions_df = get_transactions_df(start_date, now)
        latest_transactions_df['date'] = latest_transactions_df['date'].astype(str)

        all_transactions_df = pd.concat(
            [
                # TODO: Probably make sure this doesn't lead to dropped data in off-by-one?
                existing_df[existing_df['date'] < start_date],
                latest_transactions_df
            ]
        )

    else:
        latest_transactions_df = get_transactions_df(
            "2016-01-01",
            now
        )
        all_transactions_df = latest_transactions_df

    if len(all_transactions_df) == 0:
        raise ValueError("No transactions found in cache or from integration")

    if len(latest_transactions_df) == 0:
        print("No new transactions found, using only existing cached data")

    os.makedirs(EXISTING_TRANSACTIONS_FILE[:EXISTING_TRANSACTIONS_FILE.rfind("/")], exist_ok=True)
    all_transactions_df.to_csv(EXISTING_TRANSACTIONS_FILE, index=False)

    return all_transactions_df
