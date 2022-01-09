"""
This file contains the code for users making modifications to the categories
"""
import pandas as pd

from ast import literal_eval
from typing import Union

from src.utils import get_config


def add_col(df, col_name, apply_func):
    """Returns a df with an added column based on the apply_func"""
    df[col_name] = df.apply(apply_func, axis=1)
    return df


def str_or_list_to_list(val: Union[str, list]) -> list:
    """Helper to change a string or list to list"""
    if type(val) is str:
        return literal_eval(val)
    elif type(val) is list:
        return val
    else:
        raise ValueError(f"Unrecognized type: {type(val)} for {val}")


TRANSFORMATIONS = {
    'add_month': lambda df: add_col(df, 'month', lambda row: row['date'][:7]),
    'add_cat_1': lambda df: add_col(df, 'category_1', lambda row: str_or_list_to_list(row['category'])[0] if row['category'] else None),
    'add_cat_2': lambda df: add_col(df, 'category_2', lambda row: str_or_list_to_list(row['category'])[1] if len(str_or_list_to_list(row['category'])) > 1 else None),
    'important_cols': lambda df: df[['date', 'month', 'name', 'merchant_name', 'category_1', 'category_2', 'payment_channel', 'amount']],
    'remove_transfers': lambda df: df[df['name'] != ''],
}


def _text_search_bool_key(df: pd.DataFrame, term: str) -> pd.Series:
    """Helper to return a boolean series of if the term is in df['name']"""
    return df['name'].apply(lambda x: x.find(term) != -1)


def transform_df_by_funcs(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Transforms the dataframe via function that the user wants to include"""
    for filter_name in config['settings']['transformations']:
        df = TRANSFORMATIONS[filter_name](df)

    return df


def remove_transactions(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Remove transactions that contain search terms specified in config"""
    for filter_out_str in config['settings']['remove_transactions']:
        df = df[
            ~(_text_search_bool_key(df, filter_out_str))
        ]

    return df


def update_categories(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Updates categories based on any instructions in config

    NOTE: Will raise an error if category_1 does not exist
    """
    df = df.copy()
    for new_category, search_terms in config['settings']['custom_category_map'].items():
        bool_key = df.apply(lambda row: False, axis=1)

        # IMPORTANT: Sorting in reverse so that negations show up last
        for search_term in sorted(search_terms, reverse=True):
            if type(search_term) is str:

                # Negations require an &= to overwrite any non-negation rules
                if search_term[0] == '!':
                    bool_key &= ~(_text_search_bool_key(df, search_term[1:]))

                else:
                    bool_key |= _text_search_bool_key(df, search_term)

            else:
                bool_key |= df['amount'] == search_term

        df.loc[bool_key, 'category_1'] = new_category
        df.loc[bool_key, 'category_2'] = None

    return df


def transform_pipeline(df: pd.DataFrame):
    """Runs the full transformation pipeline including all user specifications"""
    config = get_config()
    df = transform_df_by_funcs(df, config)
    df = remove_transactions(df, config)

    # Will throw error if we don't have add_cat_1 as a transformation
    if 'category_1' in df:
        df = update_categories(df, config)

    return df
