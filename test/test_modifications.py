import pandas as pd
import pytest

from src.user_modifications import update_categories

SIMPLE_DF = pd.DataFrame({
    'category_1': ['Nothing', 'Nothing', 'Nothing', 'Nothing'],
    'amount': [1000, 100, 100, -5],
    'name': ['Uber', 'Uber Eats', 'LYFT', 'MOBILE DEPOS'],
})


def tmp_config(transformations=None, remove_transactions=None, custom_category_map=None):
    """Helper to easily initialize a config"""
    return {
        "settings": dict(
            transformations=transformations,
            remove_transactions=remove_transactions,
            custom_category_map=custom_category_map,
        )
    }


def test_custom_categories():
    """Tests that the categories behave as expected"""
    # Simple test
    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Uber': ['Uber']
        })
    )
    assert df['category_1'].tolist() == ['Uber', 'Uber', 'Nothing', 'Nothing']

    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Lyft': ['LYFT']
        })
    )
    assert df['category_1'].tolist() == ['Nothing', 'Nothing', 'Lyft', 'Nothing']

    # Case sensitive
    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Lyft': ['Lyft']
        })
    )
    assert df['category_1'].tolist() == ['Nothing', 'Nothing', 'Nothing', 'Nothing']

    # Multiple Categories
    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Uber': ['Uber'],
            'Lyft': ['LYFT']
        })
    )
    assert df['category_1'].tolist() == ['Uber', 'Uber', 'Lyft', 'Nothing']

    # Multiple phrases
    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Rideshare': ['Uber', 'LYFT']
        })
    )
    assert df['category_1'].tolist() == ['Rideshare', 'Rideshare', 'Rideshare', 'Nothing']

    # Negations
    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Uber': ['Uber', '!Eats']
        })
    )
    assert df['category_1'].tolist() == ['Uber', 'Nothing', 'Nothing', 'Nothing']

    # Negations
    df = update_categories(
        SIMPLE_DF,
        tmp_config(custom_category_map={
            'Uber': ['Uber', '!Eats', '!MOBILE', '!LYFT'],
            'Lyft': ['LYFT', '!MOBILE'],
        })
    )
    assert df['category_1'].tolist() == ['Uber', 'Nothing', 'Lyft', 'Nothing']
