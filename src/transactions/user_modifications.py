"""
This file contains the code for users making modifications to the categories
"""
import pandas as pd

from src.utils import get_config
from .utils import str_or_list_to_list


def add_col(df, col_name, apply_func):
    """Returns a df with an added column based on the apply_func"""
    df[col_name] = df.apply(apply_func, axis=1)
    return df


TRANSFORMATIONS = {
    'add_month': lambda df: add_col(df, 'month', lambda row: row['date'][:7]),
    'add_cat_1': lambda df: add_col(df, 'category_1', lambda row: str_or_list_to_list(row['category'])[0] if row['category'] else None),
    'add_cat_2': lambda df: add_col(df, 'category_2', lambda row: str_or_list_to_list(row['category'])[1] if len(str_or_list_to_list(row['category'])) > 1 else None),
    'important_cols': lambda df: df[['date', 'month', 'name', 'merchant_name', 'category_1', 'category_2', 'payment_channel', 'amount']],
    'remove_transfers': lambda df: df[df['name'] != ''],
}


def _text_search_bool_key(df: pd.DataFrame, term: str) -> pd.Series:
    """Helper to return a boolean series of if the term is in df['name']"""
    transaction_cols_to_check = ["name"]
    if "merchant_name" in df.columns:
        transaction_cols_to_check.append("merchant_name")

    bool_key = df["name"].apply(lambda x: False)
    for col in transaction_cols_to_check:
        bool_key |= df[col].apply(lambda x: pd.notnull(x) and x.find(term) != -1)

    return bool_key


def transform_df_by_funcs(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Transforms the dataframe via function that the user wants to include"""
    for filter_name in config['settings']['transformations']:
        df = TRANSFORMATIONS[filter_name](df)

    return df.copy()


def remove_transactions(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Remove transactions that contain search terms specified in config"""
    for filter_out_str in config['settings']['remove_transactions']:
        df = df[
            ~(_text_search_bool_key(df, filter_out_str))
        ]

    return df


def remove_accounts(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Remove transactions from specified account IDs"""
    for account_id in config['settings'].get('remove_account_ids', []):
        df = df[df["account_id"] != account_id]
    return df.copy()


def update_categories(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Updates categories based on any instructions in config

    NOTE: Will raise an error if category_1 does not exist
    """
    df = df.copy()
    for new_category, search_terms in config['settings']['custom_category_map'].items():
        bool_key = df.apply(lambda row: False, axis=1)

        # IMPORTANT: Sorting in reverse so that negations show up last
        for search_term in sorted(search_terms, key=lambda x: str(x), reverse=True):
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

    # Rename any categories the user specified
    df["category_1"] = df["category_1"].apply(
        lambda category: config["settings"]["category_renaming_map"].get(
            category, category
        )
    )

    return df


def transform_pipeline(df: pd.DataFrame):
    """Runs the full transformation pipeline including all user specifications"""
    config = get_config()
    # This has to be before transform bc we lose account_id column
    df = remove_accounts(df, config)
    df = transform_df_by_funcs(df, config)
    df = remove_transactions(df, config)

    # Will throw error if we don't have add_cat_1 as a transformation
    if 'category_1' in df:
        df = update_categories(df, config)

    return df
