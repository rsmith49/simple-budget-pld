"""
Tests for src/transactions/selection.py

Covers:
  - read_cached_transactions(): happy path, missing file, date column type
  - maybe_pull_latest_transactions(): first run (no CSV), update of existing
    data, skip when data is fresh, local-classification flag
"""
import json
import os
from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from test.conftest import SIMPLEFIN_API_RESPONSE

import src.transactions.simplefin_transactions as sf_module
from src.transactions.selection import (
    maybe_pull_latest_transactions,
    read_cached_transactions,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _setup_simplefin_mocks(monkeypatch, config: dict) -> MagicMock:
    """Patch config and HTTP for a SimpleFin pull.  Returns the mock requests."""
    mock_response = MagicMock()
    mock_response.json.return_value = SIMPLEFIN_API_RESPONSE

    mock_requests = MagicMock()
    mock_requests.get.return_value = mock_response

    monkeypatch.setattr("src.transactions.selection.get_config", lambda: config)
    monkeypatch.setattr(sf_module, "get_config", lambda: config)
    monkeypatch.setattr(sf_module, "requests", mock_requests)

    return mock_requests


# ── read_cached_transactions ───────────────────────────────────────────────────

class TestReadCachedTransactions:
    def test_returns_dataframe_when_csv_exists(
        self, tmp_path, sample_plaid_df, monkeypatch
    ):
        csv_path = str(tmp_path / "transactions.csv")
        sample_plaid_df.to_csv(csv_path, index=False)
        monkeypatch.setattr(
            "src.transactions.selection.EXISTING_TRANSACTIONS_FILE", csv_path
        )

        result = read_cached_transactions()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == len(sample_plaid_df)
        assert set(result.columns) == set(sample_plaid_df.columns)

    def test_raises_when_csv_missing(self, tmp_path, monkeypatch):
        missing = str(tmp_path / "does_not_exist.csv")
        monkeypatch.setattr(
            "src.transactions.selection.EXISTING_TRANSACTIONS_FILE", missing
        )

        with pytest.raises(FileNotFoundError):
            read_cached_transactions()

    def test_date_column_is_string(self, tmp_path, sample_plaid_df, monkeypatch):
        csv_path = str(tmp_path / "transactions.csv")
        sample_plaid_df.to_csv(csv_path, index=False)
        monkeypatch.setattr(
            "src.transactions.selection.EXISTING_TRANSACTIONS_FILE", csv_path
        )

        result = read_cached_transactions()

        assert result["date"].apply(lambda x: isinstance(x, str)).all()

    def test_round_trips_all_rows(self, tmp_path, sample_plaid_df, monkeypatch):
        csv_path = str(tmp_path / "transactions.csv")
        sample_plaid_df.to_csv(csv_path, index=False)
        monkeypatch.setattr(
            "src.transactions.selection.EXISTING_TRANSACTIONS_FILE", csv_path
        )

        result = read_cached_transactions()

        assert result["amount"].tolist() == sample_plaid_df["amount"].tolist()
        assert result["name"].tolist() == sample_plaid_df["name"].tolist()


# ── maybe_pull_latest_transactions ────────────────────────────────────────────

class TestMaybePullLatestTransactions:
    def test_creates_csv_on_first_run(
        self, patched_data_dir, simplefin_config, monkeypatch
    ):
        txn_file, _ = patched_data_dir
        _setup_simplefin_mocks(monkeypatch, simplefin_config)

        result = maybe_pull_latest_transactions()

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert os.path.exists(txn_file), "CSV should be written on first run"

    def test_saved_csv_has_required_columns(
        self, patched_data_dir, simplefin_config, monkeypatch
    ):
        txn_file, _ = patched_data_dir
        _setup_simplefin_mocks(monkeypatch, simplefin_config)

        maybe_pull_latest_transactions()

        saved = pd.read_csv(txn_file)
        for col in ("date", "name", "amount", "category"):
            assert col in saved.columns, f"Expected column '{col}' in saved CSV"

    def test_writes_pull_info_file(
        self, patched_data_dir, simplefin_config, monkeypatch
    ):
        _, pull_info_file = patched_data_dir
        _setup_simplefin_mocks(monkeypatch, simplefin_config)

        maybe_pull_latest_transactions()

        assert os.path.exists(pull_info_file)
        with open(pull_info_file) as f:
            info = json.load(f)
        assert "latest_pull" in info
        assert info["success"] is True

    def test_updates_existing_csv(
        self, patched_data_dir, simplefin_config, monkeypatch
    ):
        txn_file, _ = patched_data_dir
        # The deduplication logic in maybe_pull_latest_transactions keeps rows
        # with date < (max_date - 10 days) and replaces the rest with fresh API
        # data.  Concretely, with latest_date="2023-06-15" and GRACE=10 days,
        # start_date becomes "2023-06-05".  The two Jan rows are preserved; the
        # Jun row is replaced by the 2 mock API transactions.
        old_df = pd.DataFrame({
            "date": ["2023-01-01", "2023-01-02", "2023-06-15"],
            "name": ["OLD_A", "OLD_B", "OLD_C"],
            "merchant_name": ["M1", "M2", "M3"],
            "category": ["['X', 'Y']", "['X', 'Y']", "['X', 'Y']"],
            "payment_channel": ["online", "online", "online"],
            "amount": [10.0, 20.0, 30.0],
        })
        old_df.to_csv(txn_file, index=False)
        _setup_simplefin_mocks(monkeypatch, simplefin_config)

        result = maybe_pull_latest_transactions()

        # 2 preserved old rows + 2 new API rows = 4, which is more than the 3 original
        assert len(result) == 4
        assert {"OLD_A", "OLD_B"}.issubset(set(result["name"]))

    def test_skips_api_call_when_data_is_fresh(
        self, patched_data_dir, simplefin_config, sample_plaid_df, monkeypatch
    ):
        txn_file, pull_info_file = patched_data_dir
        sample_plaid_df.to_csv(txn_file, index=False)

        # Record a pull that happened moments ago
        with open(pull_info_file, "w") as f:
            json.dump(
                {
                    "latest_pull": datetime.now().isoformat(),
                    "latest_transaction_date": "2024-01-15",
                    "method": "simple_fin",
                    "success": True,
                },
                f,
            )

        mock_requests = _setup_simplefin_mocks(monkeypatch, simplefin_config)

        result = maybe_pull_latest_transactions()

        mock_requests.get.assert_not_called()
        assert len(result) == len(sample_plaid_df)

    def test_calls_local_classifier_when_enabled(
        self, patched_data_dir, simplefin_config, monkeypatch
    ):
        _, _ = patched_data_dir
        config_with_clf = {
            **simplefin_config,
            "settings": {
                **simplefin_config["settings"],
                "use_local_categorization": True,
            },
        }
        _setup_simplefin_mocks(monkeypatch, config_with_clf)

        mock_clf = MagicMock(side_effect=lambda df: df)  # identity — returns df unchanged
        monkeypatch.setattr(
            "src.transactions.selection.local_transaction_clf_wrapper", mock_clf
        )

        maybe_pull_latest_transactions()

        mock_clf.assert_called_once()

    def test_does_not_call_local_classifier_when_disabled(
        self, patched_data_dir, simplefin_config, monkeypatch
    ):
        _, _ = patched_data_dir
        # simplefin_config already has use_local_categorization=False
        _setup_simplefin_mocks(monkeypatch, simplefin_config)

        mock_clf = MagicMock(side_effect=lambda df: df)
        monkeypatch.setattr(
            "src.transactions.selection.local_transaction_clf_wrapper", mock_clf
        )

        maybe_pull_latest_transactions()

        mock_clf.assert_not_called()
