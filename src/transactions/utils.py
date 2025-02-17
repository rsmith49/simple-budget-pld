from ast import literal_eval
from typing import List, Union


def str_or_list_to_list(val: Union[str, list]) -> list:
    """Helper to change a string or list to list"""
    if type(val) is str:
        return literal_eval(val)
    elif type(val) is list:
        return val
    else:
        raise ValueError(f"Unrecognized type: {type(val)} for {val}")


def category_is_unknown(category: Union[List, str, None]) -> bool:
    if isinstance(category, str) or isinstance(category, list):
        return str_or_list_to_list(category)[0] == 'Unknown'
    elif category is None:
        return True
    else:
        raise ValueError(f"Unrecognized category type: {category}")
