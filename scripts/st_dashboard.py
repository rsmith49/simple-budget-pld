import altair as alt
import os
import pandas as pd
import streamlit as st
import sys
from typing import List

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
from src.transactions.user_modifications import transform_pipeline
from src.views import top_vendors
from src.utils import get_config

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


class DateInc:
    def __init__(self, date_inc: str):
        self.key = date_inc.lower()
        self.label = date_inc[0].upper() + date_inc[1:]

    def convert_iso_to_date_inc(self, date_str: str) -> str:
        """Helper to convert ISO formatted date to the date increment we care about"""
        if self.key == "week":
            return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%V')
        elif self.key == "month":
            return date_str[:7]
        elif self.key == "year":
            return date_str[:4]
        elif self.key == "day":
            return date_str[:10]
        else:
            raise ValueError(f"Unrecognized date_inc: {self.key}")

    def get_pd_range_freq(self) -> str:
        if self.key == "week":
            return "W-MON"  # Weeks starting on Monday
        elif self.key == "month":
            return "MS"  # Monthly Start
        elif self.key == "year":
            return "AS"  # Annual Start
        elif self.key == "day":
            return "D"
        else:
            raise ValueError(f"Unrecognized date_inc: {self.key}")

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


def get_dates(all_dates: pd.Series, date_inc: DateInc) -> List[str]:
    return [
        date_inc.convert_iso_to_date_inc(date.isoformat())
        for date in pd.date_range(
            all_dates.min(),
            all_dates.max(),
            freq=date_inc.get_pd_range_freq(),
        )
    ]


def monthly_spending_summary(df: pd.DataFrame, date_inc: DateInc) -> pd.DataFrame:
    grouped_df = df.groupby(date_inc.key).sum("amount")
    dates = get_dates(grouped_df.index, date_inc)
    new_df = pd.DataFrame([{"amount": 0.0} for _ in dates], index=dates)
    new_df.loc[grouped_df.index, "amount"] = grouped_df["amount"]
    return new_df.sort_index(ascending=False)


def main():
    try:
        df = get_transaction_data().copy()
        df = transform_pipeline(df)
        config = get_config()

        # Organizing Page
        st.write("# Budget Display")

        date_inc_str = st.sidebar.selectbox(
            f"Select the timespan (week, month, year) that you would like to use to view your spending by",
            ["Month", "Week", "Year"],
        )
        date_inc = DateInc(date_inc_str)

        categories_to_ignore = st.sidebar.multiselect(
            "Any categories to ignore in calculations",
            options=sorted(df["category_1"].unique()),
            default=config["settings"].get(
                "default_categories_to_ignore",
                ["Income"],
            ),
        )
        all_dates = sorted(get_dates(df["date"], DateInc("Day")))
        start_date = st.sidebar.select_slider(
            f"Enter a Start Date for viewing your spending",
            all_dates
        )
        end_date = st.sidebar.select_slider(
            f"Enter an End Date to view your spending until",
            all_dates,
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

        st.write(f"## Single {date_inc.label} in Spending")
        available_date_incs = sorted(df[date_inc.key].unique(), reverse=True)
        curr_date = st.selectbox(
            f"Pick a {date_inc.label}",
            options=available_date_incs,
            format_func=lambda label: f"{label}      ({df[df[date_inc.key] == label]['amount'].sum():,.2f})"
        )
        single_inc_spending_summary(
            df,
            date_inc.key,
            curr_date,
            is_current=curr_date == max(available_date_incs)
        )

        st.write(f"## {date_inc.label}ly Spending History")
        history_df = df_for_certain_categories(df)
        # st.bar_chart(history_df.groupby(date_inc_key).sum("amount").sort_index(ascending=False))
        st.bar_chart(monthly_spending_summary(history_df, date_inc))

        st.write(f"## Most Expensive Single {date_inc.label} Categories")
        write_df(top_vendors(df, groupby=[date_inc.key, 'category_1']))

        st.write('## Top Merchants')
        write_df(top_vendors(df, groupby='merchant_name'))

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
