from collections import Counter
from datetime import datetime
import re
from typing import Iterator, List, Optional, Tuple, Union

from dateutil.relativedelta import relativedelta
import pandas as pd

from .utils import get_config

INCREMENT_TO_DAY_MAP = {
    "month": 30.5,
    "day": 7,
}


def now() -> str:
    """String ISO Timestamp of current date"""
    return datetime.now().strftime("%Y-%m-%d")


class BudgetPeriod:
    """A helper class for dealing with dates and stuff for budgeting periods"""

    def __init__(self, period: str = "month", relative_to: str = f"{now()[:4]}-01-01"):
        """
        Parameters
        ----------
        period
            The string representation of this period. Can take the form:
                [n_](week|month), or all_time
        relative_to
            The datetime (as a string) to start counting from when determining periods.
            Defaults to the beginning of the current year
        """
        if relative_to > now():
            raise ValueError("relative_to must not be in the future")

        self.period = period
        self.relative_to = relative_to

        if self.period in ["month", "week", "quarter"]:
            self.increment = self.period
            self.unit = 1

        elif re.search(r"\d_.*", self.period):
            self.increment = self.period[2:]
            self.unit = int(self.period[0])

        else:
            raise ValueError(f"Unrecognized Period Format {self.period}")

        if self.increment == "quarter":
            self.increment = "month"
            self.unit *= 3

    def latest(self) -> str:
        """The last occurrence of this period (i.e. May 1st if period = month and today is May 15th)"""
        for start_date, _ in self.bounds_iter():
            pass

        return start_date

    def next(self) -> str:
        """The next occurrence of this period (i.e. June 1st if period = month and today is May 15th)"""
        for _, end_date in self.bounds_iter():
            pass

        return end_date

    def perc_complete(self) -> float:
        """The proportion of time through the current period"""
        latest_date = datetime.strptime(self.latest(), "%Y-%m-%d")
        next_date = datetime.strptime(self.next(), "%Y-%m-%d")

        return (datetime.now() - latest_date).days * 1.0 / (next_date - latest_date).days

    def bounds_iter(self) -> Iterator[Tuple[str, str]]:
        """An iterator that yields start & end date tuples since self.relative_to"""
        start_date = datetime.strptime(self.relative_to, "%Y-%m-%d")
        now_date = datetime.strptime(now(), "%Y-%m-%d")

        assert start_date < now_date
        while start_date < now_date:
            end_date = start_date + relativedelta(**{
                # Should only be "month" or "week" at this point
                f"{self.increment}s": self.unit
            })

            yield start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
            start_date = end_date

    def translation_multiplier(self, other_period: "BudgetPeriod") -> float:
        """Get a multiplier to indicate how to transform this period to reflect the length of another"""
        # Simple case
        if other_period.increment == self.increment:
            return other_period.unit * 1.0 / self.unit

        return (
            (
                other_period.unit * INCREMENT_TO_DAY_MAP[other_period.increment]
            ) * 1.0 / (
                self.unit * INCREMENT_TO_DAY_MAP[self.increment]
            )
        )


class BudgetItem:
    """A single budget item (category, period, TBD)"""
    def __init__(self, category: str, limit: float, period: Optional[Union[BudgetPeriod, str]]):
        """
        Parameters
        ----------
        category
            Name of the category for this item
        limit
            Budget amount for this category (over the specified period)
        period
            Period that this budget item applies to
        """
        self.category = category
        self.limit = limit

        if type(period) is str:
            period = BudgetPeriod(period)

        self.period = period

    def period_limit(self, period: BudgetPeriod) -> float:
        """Gets the translated budget amount for the period"""
        if self.period is None:
            return self.limit

        return self.limit * self.period.translation_multiplier(period)

    def on_track(self, amount_spent: float) -> bool:
        """Whether we are on track for the current period given the spending amount"""
        return self.under_projected_budget(amount_spent) >= 0

    def under_projected_budget(self, amount_spent: float) -> float:
        """The amount under budget we are currently"""
        if self.period is None:
            return self.limit - amount_spent

        return self.period.perc_complete() * self.limit - amount_spent


class TotalBudgetItem(BudgetItem):
    def __init__(self, limit: float, period: BudgetPeriod):
        super().__init__("total", limit, period)

        if self.period is None:
            raise ValueError("period cannot be None for TotalBudgetItem")


class BudgetPlan:
    """A plan with overall and categorical spending limits"""
    def __init__(
            self,
            total_budget_item: Optional[TotalBudgetItem] = None,
            category_budget_items: Optional[List[BudgetItem]] = None,
    ):
        """
        Parameters
        ----------
        total_budget_item
            The budget item for the total budget (if left empty, will use the sum of category budgets)
        category_budget_items
            The budgets for each category
        """
        if total_budget_item is None and category_budget_items is None:
            raise ValueError("Must specify one of total_budget_item or category_budget_items")

        if category_budget_items is None:
            self.category_budgets = {}
        else:
            self.category_budgets = {
                budget_item.category: budget_item
                for budget_item in category_budget_items
            }

        if total_budget_item is None:
            # Using most common period from categories for default period
            counter = Counter()
            counter.update([
                budget_item.period.period for budget_item in self.category_budgets.values()
            ])
            default_period = BudgetPeriod(counter.most_common(1)[0][0])

            total_budget_item = TotalBudgetItem(
                sum([
                    budget_item.period_limit(default_period)
                    for budget_item in self.category_budgets.values()
                ]),
                default_period,
            )

        self.total_budget_item = total_budget_item

    @classmethod
    def from_config(cls, config: dict) -> "BudgetPlan":
        """Helper to build a plan from the config.json subsection

        Parameters
        ----------
        config
            A dict of the form:
                {
                    total: float,
                    period: {
                        default: period_str,
                        category_1: period_str,
                        ...
                    },
                    categories: {
                        category_1: float,
                        category_2: float,
                        ...
                    }
                }
                where period_str take the form of:
                    [n_](week|month), or all_time
        """
        default_period = config.get("period", {}).get("default", "month")

        if config.get("total"):
            total_budget_item = TotalBudgetItem(config["total"], default_period)
        else:
            total_budget_item = None

        if config.get("categories"):
            category_budget_items = [
                BudgetItem(
                    category,
                    limit,
                    config.get("period", {}).get(category, default_period)
                )
                for category, limit in config["categories"].items()
            ]
        else:
            category_budget_items = None

        return cls(
            total_budget_item=total_budget_item,
            category_budget_items=category_budget_items
        )

# TODO: Use budgets for "you met X% of your goals over the last year" or something like that


class Budget:
    """A budget set by via config.json with overall and category spending limits"""
    def __init__(self, transactions_df: pd.DataFrame):
        self.transactions_df = transactions_df.copy()

        config = get_config()["settings"].get("budget")

        if config is not None:
            self.budget_plan = BudgetPlan.from_config(config)
        else:
            self.budget_plan = None

    def current_summary(self):
        """The breakdown of spending for the current period"""
        summary = {
            category: self._current_budget_item_summary(budget_item)
            for category, budget_item in self.budget_plan.category_budgets.items()
        }
        summary["overall"] = self._current_budget_item_summary(self.budget_plan.total_budget_item)

        return summary

    def _current_budget_item_summary(self, budget_item: BudgetItem):
        """TODO"""
        if budget_item.category == "total":
            df = self.transactions_df
        else:
            df = self.transactions_df[self.transactions_df["category_1"] == budget_item.category]

        if budget_item.period is not None:
            df = df[df["date"] >= budget_item.period.latest()]

        spending = df["amount"].sum()

        return {
            "category": budget_item.category,
            "spending": spending,
            "budget": budget_item.limit,

            "over_budget": spending > budget_item.limit,
            "under_projection_amount": budget_item.under_projected_budget(spending),
        }

    def simple_summary(self, date_inc: str, period: str) -> pd.DataFrame:
        """Returns a simple summary for a single period

        Mainly used to generate a bar chart with ticks for the budget and projected spending amounts

        Parameters
        ----------
        date_inc
            One of month, week, year
        period
            A single year, month, or week to drill into
        """
        budget_period = BudgetPeriod(date_inc)
        curr_df = self.transactions_df[self.transactions_df[date_inc] == period]
        summary = {
            "category": [],
            "spent": [],
            "total_budget": [],
            "projected_budget": [],
        }

        for category, cat_budget in self.budget_plan.category_budgets.items():
            limit = cat_budget.period_limit(budget_period)
            projected_limit = budget_period.perc_complete() * limit
            cat_spending = curr_df[curr_df["category_1"] == category]["amount"].sum()

            summary["category"].append(category)
            summary["spent"].append(cat_spending)
            summary["total_budget"].append(limit)
            summary["projected_budget"].append(projected_limit)

        # Including "Other" Category
        other_limit = self.total_limit(date_inc) - sum(summary["total_budget"])
        summary["category"].append("Other")
        summary["spent"].append(curr_df["amount"].sum() - sum(summary["spent"]))
        summary["total_budget"].append(other_limit)
        summary["projected_budget"].append(budget_period.perc_complete() * other_limit)

        return pd.DataFrame(summary)

    def total_limit(self, date_inc: str) -> float:
        """Returns the total budget limit for this period"""
        budget_period = BudgetPeriod(date_inc)
        return self.budget_plan.total_budget_item.period_limit(budget_period)
