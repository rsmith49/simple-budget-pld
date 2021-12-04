import os
import pandas as pd
import streamlit as st
import sys

from datetime import datetime
from dotenv import load_dotenv
from plaid.api_client import ApiClient
from plaid.exceptions import ApiException
from pathlib import Path
from traceback import format_exc
from urllib.error import URLError

sys.path.append(os.getcwd())
load_dotenv()

from src.transactions import get_transactions_df
from src.user_modifications import transform_pipeline
from src.views import top_vendors

EXISTING_TRANSACTIONS_FILE = f"{Path.home()}/.ry-n-shres-budget-app/all_transactions.csv"


@st.cache(
    hash_funcs={ApiClient: lambda *args, **kwargs: 0}
)
def get_transaction_data():
    try:
        existing_df = pd.read_csv(EXISTING_TRANSACTIONS_FILE)
    except FileNotFoundError:
        existing_df = None

    # Get Plaid output
    now = datetime.now().strftime('%Y-%m-%d')

    if existing_df is not None:
        latest_date = existing_df['date'].max()
        latest_transactions_df = get_transactions_df(latest_date, now)
        # So that we can set columns
        latest_transactions_df = latest_transactions_df.copy()

        # Fix for different pandas versions reading datetime objects instead of strings
        existing_df['date'] = existing_df['date'].astype(str)
        latest_transactions_df['date'] = latest_transactions_df['date'].astype(str)

        # Make sure to remove any duplicates from the final date on the original
        def key_col(df):
            return df['date'] + df['name'] + df['amount'].astype(str)

        last_date_transactions = existing_df[existing_df['date'] == latest_date].copy()
        last_date_transactions['key_col'] = key_col(last_date_transactions)
        latest_transactions_df['key_col'] = key_col(latest_transactions_df)

        latest_transactions_df = latest_transactions_df[
            ~(latest_transactions_df['key_col'].isin(last_date_transactions['key_col']))
        ]

        latest_transactions_df = latest_transactions_df.drop('key_col', axis=1)
        all_transactions_df = pd.concat([existing_df, latest_transactions_df])

    else:
        all_transactions_df = get_transactions_df('2016-01-01', '2021-06-01')

    os.makedirs(EXISTING_TRANSACTIONS_FILE[:EXISTING_TRANSACTIONS_FILE.rfind("/")], exist_ok=True)
    all_transactions_df.to_csv(EXISTING_TRANSACTIONS_FILE, index=False)

    return all_transactions_df


def write_df(df: pd.DataFrame):
    """Helper function to st.write a DF with amount stylized to dollars"""
    st.dataframe(
        df.style.format({
            col_name: "{:,.2f}"
            for col_name in ["amount", "Total Spent"]
        })
    )


def single_inc_spending_summary(df: pd.DataFrame, date_inc_key: str, curr_date: str) -> None:
    """Creates display for a single date increment"""
    curr_df = df[df[date_inc_key] == curr_date]
    st.metric(f"Total Spending", f"{curr_df['amount'].sum():,.2f}")
    st.bar_chart(curr_df.groupby("category_1").sum("amount"))

    with st.expander("Largest Transactions"):
        write_df(
            curr_df[["date", "amount", "name", "category_1", "category_2"]].sort_values(
                by="amount",
                ascending=False
            )
        )


def df_for_certain_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Helper function to get a DF filtered by any user selected categories"""
    categories = st.multiselect(
        f"Select any categories to only see spending for",
        options=sorted(df['category_1'].unique()),
        default=[],
    )

    if len(categories) > 0:
        bool_key = df['category_1'] == 'NOT_A CATEGORY'
        for cat in categories:
            bool_key = bool_key | (df['category_1'] == cat)
        df = df[bool_key]

    return df


def main():
    try:
        try:
            df = get_transaction_data().copy()
        except ApiException as e:
            # TODO: Check e for if it is item expiration
            st.write("Error accessing Plaid - using old transaction data for now")
            try:
                df = pd.read_csv(EXISTING_TRANSACTIONS_FILE)
            except FileNotFoundError:
                st.write("Could not find existing transactions file - cannot run this app")
                raise e

        df = transform_pipeline(df)

        # Organizing Page
        st.write("# Budget Display")
        date_inc = st.sidebar.selectbox(
            f"Select the timespan (week, month, year) that you would like to use to view your spending by",
            ["Month", "Week", "Year"],
        )
        date_inc_key = date_inc.lower()
        categories_to_ignore = st.sidebar.multiselect(
            "Any categories to ignore in calculations",
            options=sorted(df["category_1"].unique()),
            default=["Income"]
        )
        start_date = st.sidebar.select_slider(
            f"Enter a Start Date for viewing your spending",
            sorted(df["date"].unique())
        )
        end_date = st.sidebar.select_slider(
            f"Enter an End Date to view your spending until",
            sorted(df["date"].unique()),
            value=df["date"].max()
        )

        if start_date is not None:
            df = df[df['date'] >= start_date]
        if end_date is not None:
            df = df[df['date'] <= end_date]

        # Preprocessing
        if len(categories_to_ignore):
            for category in categories_to_ignore:
                df = df[df['category_1'] != category]

        df['week'] = df['date'].apply(lambda x: datetime.strptime(x, '%Y-%m-%d').strftime('%Y-%V'))
        if 'month' not in df:
            df['month'] = df['date'].apply(lambda x: x[:7])
        df['year'] = df['date'].apply(lambda x: x[:4])

        # Data Viz

        st.write(f"## Current {date_inc} in Spending")
        curr_date = df[date_inc_key].max()
        single_inc_spending_summary(df, date_inc_key, curr_date)

        st.write(f"## {date_inc}ly Spending History")
        history_df = df_for_certain_categories(df)
        st.bar_chart(history_df.groupby(date_inc_key).sum("amount").sort_index(ascending=False))

        st.write(f"## Single {date_inc} in Spending")
        available_date_incs = sorted(df[date_inc_key].unique(), reverse=True)
        curr_date = st.selectbox(
            f"Pick a {date_inc}",
            options=available_date_incs,
            format_func=lambda label: f"{label}      ({df[df[date_inc_key] == label]['amount'].sum():,.2f})"
        )
        single_inc_spending_summary(df, date_inc_key, curr_date)

        st.write(f"## Category by {date_inc}ly Breakdown")
        write_df(top_vendors(df, groupby=[date_inc_key, 'category_1']))

        st.write("## All Transactions")
        write_df(df)

        return

    except URLError as e:
        st.error(
            """
            **This demo requires internet access.**
    
            Connection error: %s
        """
            % e.reason
        )

    except Exception as e:
        st.error(f"""
            Something Broke :(

            Error: {e}
            Traceback: {format_exc()}
        """)


if __name__ == "__main__":
    main()
