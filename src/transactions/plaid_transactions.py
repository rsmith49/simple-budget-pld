"""
For Getting a new access token:
- Run make up language=python in the quickstart root directory
- Authenticate with WF (may need to disable 2FA apparently?)
"""
import pandas as pd
import plaid

from datetime import datetime

from plaid.api import plaid_api
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.transactions_get_request import TransactionsGetRequest

from src.utils import get_config


_plaid_client = None


def get_plaid_client():
    global _plaid_client
    if _plaid_client is None:
        creds = get_config()
        plaid_config = plaid.Configuration(
            host=plaid.Environment.Development,
            api_key=dict(
                clientId=creds['client_id'],
                secret=creds['secret']
            )
        )
        _plaid_client = plaid_api.PlaidApi(plaid.ApiClient(plaid_config))

    return _plaid_client


def get_transactions(start_date: str, end_date: str, return_metadata: bool = False):
    all_transactions = []
    creds = get_config()
    client = get_plaid_client()

    transation_args = dict(
        access_token=creds['access_token'],
        start_date=datetime.strptime(start_date, '%Y-%m-%d').date(),
        end_date=datetime.strptime(end_date, '%Y-%m-%d').date()
    )
    request = TransactionsGetRequest(**transation_args)
    response = client.transactions_get(request)

    all_transactions.extend(response['transactions'])

    while len(all_transactions) < response['total_transactions']:
        options = TransactionsGetRequestOptions()
        options.offset = len(all_transactions)

        request = TransactionsGetRequest(
            **transation_args,
            options=options
        )
        response = client.transactions_get(request)

        all_transactions.extend(response['transactions'])

    if return_metadata:
        response['transactions'] = all_transactions
        return response

    else:
        return all_transactions


def get_transactions_df(start_date, end_date):
    all_transactions = get_transactions(start_date, end_date)

    unique_keys = set()
    for transaction in all_transactions:
        unique_keys.update(transaction.to_dict().keys())

    trans_data = {
        key: []
        for key in unique_keys
    }

    for transaction in all_transactions:
        for key in unique_keys:
            if key in transaction:
                trans_data[key].append(transaction[key])
            else:
                trans_data[key].append(None)

    return pd.DataFrame(trans_data)


# TODO: Figure out how to update the link tokens
def create_link_token():
    try:
        request = LinkTokenCreateRequest(
            access_token="",
            client_name="Plaid Quickstart",
            country_codes=list(map(lambda x: CountryCode(x), PLAID_COUNTRY_CODES)),
            language='en',
            user=LinkTokenCreateRequestUser(
                client_user_id=str(time.time())
            ),
            redirect_uri="",
        )

        # create link token
        response = client.link_token_create(request)
        return jsonify(response.to_dict())
    except plaid.ApiException as e:
        return json.loads(e.body)
