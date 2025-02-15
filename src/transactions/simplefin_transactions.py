from datetime import datetime
from typing import Optional

import pandas as pd
import requests

from src.utils import epoch_to_iso, get_config, iso_to_epoch

SIMPLEFIN_URL = "https://beta-bridge.simplefin.org/simplefin/accounts"


def request_transactions_raw(start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
    # Make request
    auth = tuple(get_config()["simplefin_auth"].split(":"))

    params = {"start-date": iso_to_epoch(start_date)}
    if end_date is not None:
        params["end-date"] = iso_to_epoch(end_date)

    all_info = requests.get(
        SIMPLEFIN_URL,
        auth=auth,
        params=params,
    ).json()

    # Aggregate transactions
    all_transactions = []
    for account in all_info["accounts"]:
        account_info = {
            "account_" + key: val
            for key, val in account.items()
            if key != "transactions"
        }
        curr_transactions = [
            {
                **account_info,
                **transaction,
            }
            for transaction in account["transactions"]
        ]
        all_transactions.extend(curr_transactions)

    return pd.DataFrame(all_transactions)


# Map to convert the SimpleFin info into Plaid format
PLAID_FROM_SF_MAP = {
    "amount": lambda row: -float(row["amount"]),
    "date": lambda row: epoch_to_iso(row["transacted_at"])[:10],
    "name": lambda row: row["description"],
    "merchant_name": lambda row: row["payee"],
    "payment_channel": lambda row: "unknown",
    "category": lambda row: ['Unknown', 'Unknown'],
}


def get_transactions_df(start_date: str, end_date: Optional[str] = None) -> pd.DataFrame:
    df = request_transactions_raw(start_date, end_date)

    for key, fn in PLAID_FROM_SF_MAP.items():
        df[key] = df.apply(fn, axis=1)

    return df
