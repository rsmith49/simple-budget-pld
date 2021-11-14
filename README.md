# simple-budget-pld

A simple self hosted budget app (using streamlit or gspread) that uses plaid to fetch transaction data, and creates views for your recent and historical spending.

## Features

#### Automatic Transaction History Updates

We use Plaid to automatically sync your latest transaction data. Plaid doesn't seem like the most secure service, but for people who are comfortable giving up a little security for convenience, this project seeks to serve as a self-hosted and customizable alternative to something like Mint.

#### Streamlit Dashboard

You can view and track your most recent and historical spending using a `streamlit` created dashboard (as well as make any modifications to the data being displayed just by editing the Streamlit script). This makes seeing the data visualizations you care about much simpler, so that you don't have to settle for whatever default views some third part budgeting/expense-tracking app provides.

#### Google Sheets View

Alternatively, you can also upload your transactions directly to Google Sheets via `gspread`, and create your own visualization methods there. this was my original intent before running across `streamlit`, before realized I would prefer a native python solution to visualizing my spending and budget. I left the existing integration for creating the transaction history in a spreadsheet of your choice though, in case anyone wants this functionality.

#### Custom Data Transformations

The `config.json` file provides a set of custom data transformations in case people want to configure their data in any specific way. These include

- `transformations`: Out of the box transformations of the data from Plaid. Current options are
  - `add_month` - Creating a `month` column based on the transaction date
  - `add_cat_1` - Add the primary category from the category list that Plaid provides
  - `add_cat_2` - Add the secondary category from the category list that Plaid provides
  - `important_cols` - Only use the "important" columns when loading the resulting data. These can be found in `src/user_modifications.py`
- `remove_transactions`: A list of search terms to remove transactions whose `name` contains the term. This can be helpful for removing things like credit card payments, or other transfers between accounts.
- `custom_category_map`: Map any categories (new or existing) to search terms match against `name`, or specific dollar amounts to match against `amount`. This is helpful for autocategorizing spending from a frequent vendor, or putting recurring payments easily into a category (like "Rent").

## Setup and Installation

1. Create a Plaid Development account and get the client key and secret, then store them in `.env`
2. Clone the `plaid/quickstart` and follow the steps to retrieve an `access_token` and `item_id`. Then put them in `.env`
3. (Optional for Sheets) If using the Google Sheets integration, add the sheet ID to `.env` (have to share with the service account, forget how this works)
    - TODO
4. Create a virtualenv and install the correct requirements (`dashboard_requirements.txt` for using `st_dashboard`, `sheet_requirements.txt` for using sheets, `base_requirements.txt` for just getting a dataframe from the plaid integration)
5. Run

```streamlit run scripts/st_dashboard.py```

and go to the localhost address displayed to access your budget app.

## Customization

TODO
