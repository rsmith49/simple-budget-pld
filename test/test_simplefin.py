"""
Tests for src/transactions/simplefin_transactions.py

Covers:
  - request_transactions_raw(): API call, auth forwarding, account-info merge
  - get_transactions_df(): amount negation, date format, field mapping,
    default Unknown category assignment
"""
from unittest.mock import MagicMock

import pandas as pd
import pytest

from test.conftest import SIMPLEFIN_API_RESPONSE

import src.transactions.simplefin_transactions as sf_module
from src.transactions.simplefin_transactions import (
    get_transactions_df,
    request_transactions_raw,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_http(monkeypatch, config, response_body=SIMPLEFIN_API_RESPONSE):
    """Patch requests and get_config in simplefin_transactions."""
    mock_response = MagicMock()
    mock_response.json.return_value = response_body

    mock_requests = MagicMock()
    mock_requests.get.return_value = mock_response

    monkeypatch.setattr(sf_module, "requests", mock_requests)
    monkeypatch.setattr(sf_module, "get_config", lambda: config)

    return mock_requests


# ── request_transactions_raw ──────────────────────────────────────────────────

class TestRequestTransactionsRaw:
    def test_calls_simplefin_url(self, simplefin_config, monkeypatch):
        mock_requests = _mock_http(monkeypatch, simplefin_config)

        request_transactions_raw("2024-01-01", "2024-01-31")

        mock_requests.get.assert_called_once()
        call_url = mock_requests.get.call_args.args[0]
        assert "simplefin" in call_url

    def test_passes_auth_from_config(self, simplefin_config, monkeypatch):
        mock_requests = _mock_http(monkeypatch, simplefin_config)

        request_transactions_raw("2024-01-01", "2024-01-31")

        call_kwargs = mock_requests.get.call_args.kwargs
        # simplefin_config["simplefin_auth"] = "user:password"
        assert call_kwargs["auth"] == ("user", "password")

    def test_passes_start_date_as_epoch(self, simplefin_config, monkeypatch):
        mock_requests = _mock_http(monkeypatch, simplefin_config)

        request_transactions_raw("2024-01-01", "2024-01-31")

        call_kwargs = mock_requests.get.call_args.kwargs
        assert "start-date" in call_kwargs["params"]
        assert isinstance(call_kwargs["params"]["start-date"], int)

    def test_returns_all_transactions_as_dataframe(
        self, simplefin_config, monkeypatch
    ):
        _mock_http(monkeypatch, simplefin_config)

        result = request_transactions_raw("2024-01-01", "2024-01-31")

        assert isinstance(result, pd.DataFrame)
        # SIMPLEFIN_API_RESPONSE has 1 account with 2 transactions
        assert len(result) == 2

    def test_merges_account_id_into_each_row(self, simplefin_config, monkeypatch):
        _mock_http(monkeypatch, simplefin_config)

        result = request_transactions_raw("2024-01-01", "2024-01-31")

        assert "account_id" in result.columns
        assert (result["account_id"] == "acct_001").all()

    def test_omits_end_date_param_when_none(self, simplefin_config, monkeypatch):
        mock_requests = _mock_http(monkeypatch, simplefin_config)

        request_transactions_raw("2024-01-01")  # no end_date

        call_kwargs = mock_requests.get.call_args.kwargs
        assert "end-date" not in call_kwargs["params"]


# ── get_transactions_df ───────────────────────────────────────────────────────

class TestGetTransactionsDf:
    def test_negates_simplefin_amounts(self, simplefin_config, monkeypatch):
        """SimpleFin uses negative for debits; Plaid convention is positive."""
        _mock_http(monkeypatch, simplefin_config)

        result = get_transactions_df("2024-01-01")

        # Source amounts are "-42.50" and "-12.99"; expect positive floats
        assert (result["amount"] > 0).all()
        assert set(round(a, 2) for a in result["amount"]) == {42.50, 12.99}

    def test_date_is_ten_char_iso_string(self, simplefin_config, monkeypatch):
        _mock_http(monkeypatch, simplefin_config)

        result = get_transactions_df("2024-01-01")

        assert result["date"].apply(lambda d: len(d) == 10 and d[4] == "-").all()

    def test_maps_description_to_name(self, simplefin_config, monkeypatch):
        _mock_http(monkeypatch, simplefin_config)

        result = get_transactions_df("2024-01-01")

        assert set(result["name"]) == {"WHOLE FOODS MARKET", "NETFLIX"}

    def test_maps_payee_to_merchant_name(self, simplefin_config, monkeypatch):
        _mock_http(monkeypatch, simplefin_config)

        result = get_transactions_df("2024-01-01")

        assert set(result["merchant_name"]) == {"Whole Foods", "Netflix"}

    def test_category_defaults_to_unknown(self, simplefin_config, monkeypatch):
        _mock_http(monkeypatch, simplefin_config)

        result = get_transactions_df("2024-01-01")

        assert all(result["category"].apply(lambda c: c == ["Unknown", "Unknown"]))

    def test_payment_channel_is_unknown(self, simplefin_config, monkeypatch):
        _mock_http(monkeypatch, simplefin_config)

        result = get_transactions_df("2024-01-01")

        assert (result["payment_channel"] == "unknown").all()

    def test_multiple_accounts_are_combined(self, simplefin_config, monkeypatch):
        two_account_response = {
            "accounts": [
                {
                    "id": "acct_001",
                    "name": "Checking",
                    "currency": "USD",
                    "balance": "1000.00",
                    "balance-date": 1704153600,
                    "transactions": [
                        {
                            "id": "txn_A",
                            "amount": "-10.00",
                            "description": "Shop A",
                            "payee": "Payee A",
                            "transacted_at": 1704110400,
                        }
                    ],
                },
                {
                    "id": "acct_002",
                    "name": "Savings",
                    "currency": "USD",
                    "balance": "5000.00",
                    "balance-date": 1704153600,
                    "transactions": [
                        {
                            "id": "txn_B",
                            "amount": "-20.00",
                            "description": "Shop B",
                            "payee": "Payee B",
                            "transacted_at": 1704110400,
                        }
                    ],
                },
            ]
        }
        _mock_http(monkeypatch, simplefin_config, two_account_response)

        result = get_transactions_df("2024-01-01")

        assert len(result) == 2
        assert set(result["account_id"]) == {"acct_001", "acct_002"}
