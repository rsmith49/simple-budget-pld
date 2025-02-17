"""
Local Categorization of transactions (if not provided by external APIs)
"""
from typing import Any, Dict

import pandas as pd
from transformers import Pipeline, pipeline

from .utils import category_is_unknown

_TRANS_CLF = None

# Parent categories for the classifier we are using
MGRELLA_CAT1S = [
    "BILLS_SUBSCRIPTIONS",
    "CREDIT_CARDS",
    "EATING_OUT",
    "HEALTH_WELLNESS",
    "HOUSING_FAMILY",
    "LEISURE",
    "MORTGAGES_LOANS",
    "OTHER",
    "PROFITS",
    "SHOPPING",
    "TAXES_SERVICES",
    "TRANSFERS",
    "TRAVELS_TRANSPORTATION",
    "WAGES",
]


def transaction_clf() -> Pipeline:
    """Lazy load transaction classifier"""
    global _TRANS_CLF
    if _TRANS_CLF is None:
        _TRANS_CLF = pipeline(
            "text-classification",
            model="mgrella/autonlp-bank-transaction-classification-5521155",
        )

    return _TRANS_CLF


def convert_to_category_list_str(clf_output: Dict[str, Any]) -> str:
    """Converts the HF pipeline output to the format used by Plaid"""
    cat_str = clf_output["label"]
    for tier_1_cat in MGRELLA_CAT1S:
        # Need the Category. prefix so that we don't match on sub-category
        if "Category." + tier_1_cat in cat_str:
            return str([
                tier_1_cat,
                cat_str[cat_str.find(tier_1_cat) + len(tier_1_cat) + 1:],
            ])

    raise ValueError(f"Could not find an appropriate category for '{cat_str}'")


def classify_unknowns(df: pd.DataFrame) -> pd.DataFrame:
    # TODO: Abstract out the definition of "Unknown" category
    is_unknown_bool_key = df["category"].apply(category_is_unknown)
    if is_unknown_bool_key.sum() == 0:
        # All already categorized
        return df

    clf = transaction_clf()
    transaction_names = df[is_unknown_bool_key]["name"]
    clf_outputs = clf(
        transaction_names.tolist(),
        batch_size=128,
    )
    predicted_categories = [
        convert_to_category_list_str(clf_output)
        for clf_output in clf_outputs
    ]

    new_df = df.copy()
    new_df.loc[is_unknown_bool_key, "category"] = predicted_categories
    return new_df
