from typing import Any, Optional

import pandas as pd


def top_vendors(df: pd.DataFrame, groupby: Any = 'name', limit: Optional[int] = None):
    """Return a DataFrame of top vendors"""
    new_df = df.groupby(groupby).agg(**{
        'Total Spent': ('amount', 'sum'),
        'Total Transactions': ('name', 'count'),
        'Last Transaction': ('date', 'max')
    }).sort_values('Total Spent', ascending=False).reset_index()

    if limit is not None:
        new_df = new_df.head(limit)

    return new_df


# Dict of useful groupby/aggregations for creating views on payment data from a DF
VIEW_FUNCS = {
    'Top Transactions': lambda df: df.sort_values('amount', ascending=False),
    'Top Vendors': lambda df: top_vendors(df),
    'Top Merchants': lambda df: top_vendors(df, groupby='merchant_name'),
    'Monthly Summary': lambda df: top_vendors(df, groupby=['month', 'category_1']),
}

# TODO:
#   - Add account name column
#   - Make a view for month by month trends
#   - Figure out if we just want current month, or if we should keep records of previous months
