"""
Shared fixtures and test infrastructure for the simple-budget-pld test suite.

Plaid-python doesn't build in this environment (and is never exercised by the
SimpleFin code path we're testing), so we inject a MagicMock for all plaid
sub-modules before any application module is imported.
"""
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest


# ── Plaid stub (module-level — runs before any app imports) ───────────────────

def _install_plaid_mock() -> None:
    """Prevent ImportError when plaid-python is not installed."""
    if "plaid" in sys.modules:
        return
    _stub = MagicMock()
    for name in [
        "plaid",
        "plaid.api",
        "plaid.api.plaid_api",
        "plaid.model",
        "plaid.model.transactions_get_request",
        "plaid.model.transactions_get_request_options",
    ]:
        sys.modules.setdefault(name, _stub)


_install_plaid_mock()


# ── Shared constant: mock SimpleFin API response ───────────────────────────────

#: Mirrors the shape returned by the SimpleFin Bridge /accounts endpoint.
SIMPLEFIN_API_RESPONSE = {
    "accounts": [
        {
            "id": "acct_001",
            "name": "Checking Account",
            "currency": "USD",
            "balance": "1234.56",
            "balance-date": 1704153600,
            "transactions": [
                {
                    "id": "txn_001",
                    "amount": "-42.50",
                    "description": "WHOLE FOODS MARKET",
                    "payee": "Whole Foods",
                    # 2024-01-02 12:00 UTC — well within any timezone's Jan 2
                    "transacted_at": 1704196800,
                },
                {
                    "id": "txn_002",
                    "amount": "-12.99",
                    "description": "NETFLIX",
                    "payee": "Netflix",
                    # 2024-01-01 12:00 UTC
                    "transacted_at": 1704110400,
                },
            ],
        }
    ]
}


# ── Shared fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def sample_plaid_df() -> pd.DataFrame:
    """Small DataFrame in Plaid-compatible format with known categories."""
    return pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02", "2024-01-15"],
        "name": ["WHOLE FOODS MARKET", "NETFLIX", "STARBUCKS"],
        "merchant_name": ["Whole Foods", "Netflix", "Starbucks"],
        "category": [
            "['SHOPPING', 'Groceries']",
            "['BILLS_SUBSCRIPTIONS', 'Streaming']",
            "['EATING_OUT', 'Coffee']",
        ],
        "payment_channel": ["in store", "online", "in store"],
        "amount": [42.50, 12.99, 5.75],
    })


@pytest.fixture
def unknown_category_df() -> pd.DataFrame:
    """Transactions with Unknown categories, as SimpleFin provides them."""
    return pd.DataFrame({
        "date": ["2024-01-01", "2024-01-02"],
        "name": ["WHOLE FOODS MARKET", "NETFLIX"],
        "merchant_name": ["Whole Foods", "Netflix"],
        "category": ["['Unknown', 'Unknown']", "['Unknown', 'Unknown']"],
        "payment_channel": ["in store", "online"],
        "amount": [42.50, 12.99],
    })


@pytest.fixture
def simplefin_config() -> dict:
    """Minimal config dict that selects the SimpleFin transaction source."""
    return {
        "simplefin_auth": "user:password",
        "settings": {
            "use_local_categorization": False,
            "transformations": ["add_month", "add_cat_1", "add_cat_2", "important_cols"],
            "remove_transactions": [],
            "custom_category_map": {},
            "category_renaming_map": {},
        },
    }


@pytest.fixture
def patched_data_dir(tmp_path, monkeypatch):
    """Redirect the app's CSV and pull-info paths to an isolated temp directory.

    Returns (transactions_csv_path, pull_info_json_path).
    """
    import src.transactions.selection as sel

    txn_file = str(tmp_path / "transactions.csv")
    pull_info_file = str(tmp_path / "pull_info.json")
    monkeypatch.setattr(sel, "EXISTING_TRANSACTIONS_FILE", txn_file)
    monkeypatch.setattr(sel, "TRANSACTIONS_PULL_INFO_FILE", pull_info_file)
    return txn_file, pull_info_file


@pytest.fixture
def mocked_classifier(monkeypatch):
    """Inject a mock HuggingFace pipeline so classification tests run without
    torch/transformers being installed.

    Returns the MagicMock instance that acts as the loaded classifier.
    Set ``mocked_classifier.return_value`` to control prediction output.
    """
    mock_clf_instance = MagicMock()
    mock_tf = MagicMock()
    mock_tf.Pipeline = type("MockPipeline", (), {})
    mock_tf.pipeline = MagicMock(return_value=mock_clf_instance)

    # Replace transformers with our mock so classification.py can be imported.
    monkeypatch.setitem(sys.modules, "transformers", mock_tf)
    # Force re-import of the classification module so it picks up the mock.
    monkeypatch.delitem(sys.modules, "src.transactions.classification", raising=False)

    return mock_clf_instance
