#!/usr/bin/env python3
"""Standalone transaction-update script.

This is the entrypoint for the Cloud Run Job that runs on a schedule (via
Cloud Scheduler).  It pulls the latest transactions from SimpleFin / Plaid,
classifies them, and writes the result to the shared GCS-mounted directory
so the dashboard picks up fresh data on the next page load.

Usage (local):
    python scripts/update_transactions.py

Usage (Cloud Run Job):
    Configured automatically via cloud/job.yaml.  The GCS bucket is mounted
    at /root/.ry-n-shres-budget-app/ so the CSV and pull-info JSON are
    persisted between runs.
"""
import os
import sys

sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from src.transactions.selection import maybe_pull_latest_transactions


def main() -> None:
    print("Starting transaction update...")
    df = maybe_pull_latest_transactions()
    print(f"Done. {len(df)} total transactions stored.")


if __name__ == "__main__":
    main()
