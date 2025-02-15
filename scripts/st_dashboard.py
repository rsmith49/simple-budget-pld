import altair as alt
import os
import pandas as pd
import streamlit as st
import sys

from datetime import datetime
from dotenv import load_dotenv
from plaid.api_client import ApiClient
from plaid.exceptions import ApiException
from traceback import format_exc
from urllib.error import URLError

sys.path.append(os.getcwd())
load_dotenv()

from src.budget import Budget
from src.transactions.selection import maybe_pull_latest_transactions
from src.user_modifications import transform_pipeline
from src.views import top_vendors

st.set_page_config(initial_sidebar_state="collapsed")


@st.cache(
    hash_funcs={ApiClient: lambda *args, **kwargs: 0}
)
def get_transaction_data():
    all_transactions_df = maybe_pull_latest_transactions()

    # Fix for Streamlit Cache issues
    for col in ["payment_meta", "location"]:
        if col in all_transactions_df.columns:
            all_transactions_df = all_transactions_df.drop(col, axis=1)
    all_transactions_df["category"] = all_transactions_df["category"].astype(str)

    return all_transactions_df


def write_df(df: pd.DataFrame):
    """Helper function to st.write a DF with amount stylized to dollars"""
    st.dataframe(
        df.style.format({
            col_name: "{:,.2f}"
            for col_name in ["amount", "Total Spent"]
        })
    )

# TODO: Make non-budgeted columns show up on bar chart, just without ticks
# TODO: Make all-time a budget period option (figure out what to do about this - maybe it only shows up for one month?)
# TODO: Allow you to set custom start date for your budget period (i.e. make your monthly spending start on the 3rd)
# TODO: Fix the duplicate charge issue with pending charges


def single_inc_spending_summary(df: pd.DataFrame, date_inc_key: str, curr_date: str, is_current: bool = False) -> None:
    """Creates display for a single date increment

    Parameters
    ----------
    df
        Transactions Dataframe
    date_inc_key
        The key for date increment (one of week, month, year)
    curr_date
        The selected date increment value
    is_current
        Whether the date represents the most recent date increment
    """
    budget = Budget(df)
    curr_df = df[df[date_inc_key] == curr_date]
    total_spending_str = f"{curr_df['amount'].sum():,.2f}"

    if budget.budget_plan:
        show_budget = st.checkbox("Budget View", value=True)
        total_budget = budget.total_limit(date_inc_key)

    if budget.budget_plan and show_budget:
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            st.metric(f"Total Spending", total_spending_str)
        with metric_col2:
            st.metric(f"Total Budget", f"{total_budget:,.2f}")

        simple_summary = budget.simple_summary(date_inc_key, curr_date)
        bar = alt.Chart(simple_summary).mark_bar().encode(
            y="category",
            x="spent",
            tooltip=alt.Tooltip(field="spent", aggregate="sum", type="quantitative"),
        ).properties(
            height=alt.Step(60)
        )

        ticks = alt.Chart(simple_summary).mark_tick(
            color="red",
            thickness=3,
            size=60 * 0.9,
        ).encode(
            y="category",
            x="total_budget",
            tooltip=alt.Tooltip(field="total_budget", aggregate="sum", type="quantitative")
        )

        if is_current:
            ticks += alt.Chart(simple_summary).mark_tick(
                color="white",
                thickness=2,
                size=60 * 0.9,
            ).encode(
                y="category",
                x="projected_budget",
            )

        st.altair_chart(bar + ticks, use_container_width=True)

    else:
        st.metric(f"Total Spending", total_spending_str)

        chart = alt.Chart(curr_df).mark_bar().encode(
            x=alt.X("sum(amount)", axis=alt.Axis(title='Spent')),
            y=alt.Y("category_1", axis=alt.Axis(title="Category")),
            tooltip=alt.Tooltip(field="amount", aggregate="sum", type="quantitative"),
        ).properties(
            height=alt.Step(40),
        )

        st.altair_chart(chart, use_container_width=True)

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
            st.error(f"{e}")
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
        date_inc_label = date_inc[0].upper() + date_inc[1:]

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

        st.write(f"## Single {date_inc_label} in Spending")
        available_date_incs = sorted(df[date_inc_key].unique(), reverse=True)
        curr_date = st.selectbox(
            f"Pick a {date_inc_label}",
            options=available_date_incs,
            format_func=lambda label: f"{label}      ({df[df[date_inc_key] == label]['amount'].sum():,.2f})"
        )
        single_inc_spending_summary(
            df,
            date_inc_key,
            curr_date,
            is_current=curr_date == max(available_date_incs)
        )

        st.write(f"## {date_inc_label}ly Spending History")
        history_df = df_for_certain_categories(df)
        st.bar_chart(history_df.groupby(date_inc_key).sum("amount").sort_index(ascending=False))

        st.write(f"## Most Expensive Single {date_inc} Categories")
        write_df(top_vendors(df, groupby=[date_inc_key, 'category_1']))

        st.write("## All Transactions")
        write_df(df)

        # TODO: Figure out how we want to show the various conflicting budget periods
        #       - Do we want the triple layered bar chart still? (spending / projected / limit)
        #       - Do we just want 2 views? How can we give category level info well

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
