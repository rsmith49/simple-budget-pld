try:
    import gspread
except ImportError:
    raise RuntimeError("Need to run `pip install -r sheets_requirements.txt` to use sheets functionality")

import re
import pandas as pd
import numpy as np

from gspread.utils import a1_to_rowcol, rowcol_to_a1

from .views import VIEW_FUNCS
from .utils import get_config

gc = gspread.service_account()


def df_to_ws(
        worksheet: gspread.Worksheet,
        df: pd.DataFrame,
        start_location: str = 'A!',
        include_headers: bool = True
) -> None:
    """
    Updates the worksheet with the dataframe in the specified location
    :param worksheet:
    :param df:
    :param start_location:
    :param include_headers:
    """
    values = df.values.tolist()
    if include_headers:
        values = [df.columns.values.tolist()] + values

    worksheet.update(
        start_location,
        values
    )


def ws_to_df(worksheet: gspread.Worksheet, start_location: str = 'A1') -> pd.DataFrame:
    """
    Get a DataFrame from a worksheet, optionally starting at a specified location
    :param worksheet:
    :param start_location:
    :return:
    """
    start_row, start_col = a1_to_rowcol(start_location)
    last_col_cell = worksheet.findall(
        re.compile('.*'),
        in_row=start_row
    )[-1]

    last_row_cell = worksheet.findall(
        re.compile('.+'),
        in_column=start_col
    )[-1]

    last_row = last_row_cell.row
    last_col = last_col_cell.col

    data_arr = np.array(
        worksheet.get_values(f'{start_location}:{rowcol_to_a1(last_row, last_col)}')
    )

    return pd.DataFrame(data=data_arr[1:, :], columns=data_arr[0, :])


class BudgetSpreadsheet:
    """The control flow for updating spreadsheets with the given budget transactions"""
    def __init__(self):
        config = get_config()
        self.spreadsheet = gc.open_by_key(config['budget_spreadsheet_id'])
        self.transactions_sheet = self.spreadsheet.worksheet('Transactions')

        try:
            self.transactions_df = ws_to_df(self.transactions_sheet)
            self.transactions_df["amount"] = self.transactions_df["amount"].apply(
                lambda x: x.replace("$", "") if type(x) is str else x
            )
        except Exception as e:
            # Print the exception, but proceed
            print(e)
            self.transactions_df = None

    def budget_sheet(self, name):
        return BudgetWorksheet(
            self.spreadsheet.worksheet(name),
            self.transactions_df
        )


class BudgetWorksheet:
    """Implementing some helpful methods in addition to those already provided"""
    def __init__(self, worksheet: gspread.Worksheet, transactions_df: pd.DataFrame):
        self.worksheet = worksheet
        self.transactions_df = transactions_df

    def _template_update_cell(self, cell: gspread.Cell, update_now: bool = True) -> bool:
        """
        Updates a single cell for templating commands
        :param cell:
        :return: Whether the cell should be updated after this method
        """
        # TODO: Figure out if there are any single cell values or expressions we want
        should_update = False
        expression = cell.value[2:-2]

        if expression in VIEW_FUNCS:
            view_df = VIEW_FUNCS[expression](self.transactions_df)
            df_to_ws(self.worksheet, view_df, start_location=cell.address)

        elif expression == 'TESTING':
            cell.value = 'TESTED!'
            should_update = True

        if update_now and should_update:
            self.worksheet.update_cell(cell.row, cell.col, cell.value)

        return should_update

    def template_update(self) -> None:
        """
        Updates the spreadsheet looking for templating commands
        """
        cells_to_update = []
        reg = re.compile('{{.+}}')
        cells = self.worksheet.findall(reg)

        for cell in cells:
            if self._template_update_cell(cell, update_now=False):
                cells_to_update.append(cell)

        self.worksheet.update_cells(cells_to_update)


