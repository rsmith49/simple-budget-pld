import sys
import os

sys.path.append(os.getcwd())

from datetime import datetime

from src.transactions import get_transactions_df
from src.sheets import BudgetSpreadsheet, df_to_ws
from src.user_modifications import transform_pipeline


def _transactions_df_pipeline(latest_date='2016-01-01'):
    """
    Returns a transactions DF with all filters and what not applied
    :param latest_date:
    :return:
    """
    now = datetime.now().strftime('%Y-%m-%d')

    latest_transactions_df = get_transactions_df(latest_date, now)
    latest_transactions_df = transform_pipeline(latest_transactions_df)

    return latest_transactions_df


def update_transactions() -> None:
    """
    Single function to call that updates the transactions in a spreadsheet based on
    """
    # Get Sheet
    bsh = BudgetSpreadsheet()
    latest_date = bsh.transactions_df['date'].max()

    # Get Plaid output
    latest_transactions_df = _transactions_df_pipeline(latest_date)

    # So that we can set columns
    latest_transactions_df = latest_transactions_df.copy()

    # Make sure to remove any duplicates from the final date on the original
    def key_col(df):
        return df['date'] + df['name'] + df['amount'].astype(str)

    last_date_transactions = bsh.transactions_df[bsh.transactions_df['date'] == latest_date].copy()
    last_date_transactions['key_col'] = key_col(last_date_transactions)
    latest_transactions_df['key_col'] = key_col(latest_transactions_df)

    latest_transactions_df = latest_transactions_df[
        ~(latest_transactions_df['key_col'].isin(last_date_transactions['key_col']))
    ]

    latest_transactions_df = latest_transactions_df.drop('key_col', axis=1)

    if len(latest_transactions_df) > 0:
        df_to_ws(
            bsh.spreadsheet.worksheet('Transactions'),
            latest_transactions_df.sort_values('date'),         # Want to sort by transaction date ascending
            start_location=f'A{len(bsh.transactions_df) + 2}',  # +1 for headers row, +1 for index starting at 1 not 0
            include_headers=False
        )


def create_transactions() -> None:
    """
    Single function call that creates (or overwrites) all the transactions in the spreadsheet
    (uses from date 2016-01-01)
    """
    bsh = BudgetSpreadsheet()
    latest_transactions_df = _transactions_df_pipeline()

    df_to_ws(
        bsh.spreadsheet.worksheet('Transactions'),
        latest_transactions_df.sort_values('date'),  # Want to sort by transaction date ascending
        start_location=f'A1',
        include_headers=True
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "start":
        create_transactions()
    else:
        update_transactions()


if __name__ == "__main__":
    main()
