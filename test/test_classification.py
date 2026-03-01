"""
Tests for src/transactions/classification.py and the
local_transaction_clf_wrapper in src/transactions/selection.py

The mocked_classifier fixture (defined in conftest.py) injects a fake
'transformers' module so these tests run without torch being installed.
"""
import sys

import pandas as pd
import pytest


# ── convert_to_category_list_str ─────────────────────────────────────────────

class TestConvertToCategoryListStr:
    """Unit tests for the HuggingFace-output → Plaid-string converter."""

    def _convert(self, label: str, mocked_classifier) -> str:
        from src.transactions.classification import convert_to_category_list_str
        return convert_to_category_list_str({"label": label, "score": 0.9})

    def test_shopping_category(self, mocked_classifier):
        result = self._convert("Category.SHOPPING_Groceries", mocked_classifier)
        assert result == "['SHOPPING', 'Groceries']"

    def test_bills_subscriptions_category(self, mocked_classifier):
        result = self._convert(
            "Category.BILLS_SUBSCRIPTIONS_Streaming", mocked_classifier
        )
        assert result == "['BILLS_SUBSCRIPTIONS', 'Streaming']"

    def test_eating_out_category(self, mocked_classifier):
        result = self._convert("Category.EATING_OUT_Coffee", mocked_classifier)
        assert result == "['EATING_OUT', 'Coffee']"

    def test_travels_transportation_category(self, mocked_classifier):
        result = self._convert(
            "Category.TRAVELS_TRANSPORTATION_Rideshare", mocked_classifier
        )
        assert result == "['TRAVELS_TRANSPORTATION', 'Rideshare']"

    def test_raises_for_unrecognised_label(self, mocked_classifier):
        from src.transactions.classification import convert_to_category_list_str
        with pytest.raises(ValueError, match="Could not find an appropriate category"):
            convert_to_category_list_str({"label": "UNKNOWN_FORMAT", "score": 0.5})


# ── classify_unknowns ─────────────────────────────────────────────────────────

class TestClassifyUnknowns:
    def test_classifies_all_unknown_transactions(
        self, mocked_classifier, unknown_category_df
    ):
        mocked_classifier.return_value = [
            {"label": "Category.SHOPPING_Groceries", "score": 0.95},
            {"label": "Category.BILLS_SUBSCRIPTIONS_Streaming", "score": 0.88},
        ]

        from src.transactions.classification import classify_unknowns
        result = classify_unknowns(unknown_category_df)

        assert result.loc[0, "category"] == "['SHOPPING', 'Groceries']"
        assert result.loc[1, "category"] == "['BILLS_SUBSCRIPTIONS', 'Streaming']"

    def test_skips_already_categorised_rows(self, mocked_classifier):
        """Rows with a known category must not be sent to the model."""
        df = pd.DataFrame({
            "date": ["2024-01-01", "2024-01-02"],
            "name": ["WHOLE FOODS MARKET", "NETFLIX"],
            "category": [
                "['SHOPPING', 'Groceries']",   # already known
                "['Unknown', 'Unknown']",       # needs classification
            ],
            "amount": [42.50, 12.99],
        })

        # Only one Unknown row → model is called with one item → returns one result
        mocked_classifier.return_value = [
            {"label": "Category.BILLS_SUBSCRIPTIONS_Streaming", "score": 0.88},
        ]

        from src.transactions.classification import classify_unknowns
        result = classify_unknowns(df)

        # Known row must be unchanged
        assert result.loc[0, "category"] == "['SHOPPING', 'Groceries']"
        # Unknown row gets classified
        assert result.loc[1, "category"] == "['BILLS_SUBSCRIPTIONS', 'Streaming']"

    def test_returns_unchanged_when_no_unknowns(
        self, mocked_classifier, sample_plaid_df
    ):
        """When all transactions are already categorised the pipeline is never called."""
        from src.transactions.classification import classify_unknowns
        result = classify_unknowns(sample_plaid_df)

        mocked_classifier.assert_not_called()
        pd.testing.assert_frame_equal(result, sample_plaid_df)

    def test_does_not_mutate_input_dataframe(
        self, mocked_classifier, unknown_category_df
    ):
        mocked_classifier.return_value = [
            {"label": "Category.SHOPPING_Groceries", "score": 0.9},
            {"label": "Category.EATING_OUT_Coffee", "score": 0.85},
        ]

        original_categories = unknown_category_df["category"].tolist()

        from src.transactions.classification import classify_unknowns
        classify_unknowns(unknown_category_df)

        # Input should not be modified in place
        assert unknown_category_df["category"].tolist() == original_categories

    def test_model_receives_only_unknown_transaction_names(self, mocked_classifier):
        df = pd.DataFrame({
            "name": ["WHOLE FOODS", "NETFLIX", "STARBUCKS"],
            "category": [
                "['SHOPPING', 'Groceries']",
                "['Unknown', 'Unknown']",
                "['Unknown', 'Unknown']",
            ],
            "amount": [42.50, 12.99, 5.75],
        })
        mocked_classifier.return_value = [
            {"label": "Category.BILLS_SUBSCRIPTIONS_Streaming", "score": 0.9},
            {"label": "Category.EATING_OUT_Coffee", "score": 0.85},
        ]

        from src.transactions.classification import classify_unknowns
        classify_unknowns(df)

        # The pipeline should be called with only the 2 unknown names, not all 3
        call_args = mocked_classifier.call_args
        names_passed = call_args.args[0]
        assert "WHOLE FOODS" not in names_passed
        assert "NETFLIX" in names_passed
        assert "STARBUCKS" in names_passed


# ── local_transaction_clf_wrapper ImportError handling ────────────────────────

class TestLocalClfWrapperImportError:
    def test_returns_df_unchanged_when_transformers_missing(
        self, monkeypatch, sample_plaid_df
    ):
        """When classification.py cannot be imported the wrapper must not raise."""
        # None in sys.modules causes ImportError on any attempt to import that module
        monkeypatch.setitem(sys.modules, "src.transactions.classification", None)

        from src.transactions.selection import local_transaction_clf_wrapper
        result = local_transaction_clf_wrapper(sample_plaid_df)

        pd.testing.assert_frame_equal(result, sample_plaid_df)

    def test_prints_warning_when_transformers_missing(
        self, monkeypatch, sample_plaid_df, capsys
    ):
        monkeypatch.setitem(sys.modules, "src.transactions.classification", None)

        from src.transactions.selection import local_transaction_clf_wrapper
        local_transaction_clf_wrapper(sample_plaid_df)

        captured = capsys.readouterr()
        assert "WARNING" in captured.out
        assert "transformers" in captured.out.lower() or "classification" in captured.out.lower()
