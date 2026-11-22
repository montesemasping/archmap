"""Menu catalog lookups."""
from .items import ITEMS


def list_items():
    return list(ITEMS)


def find_item(item_id):
    return next((i for i in ITEMS if i["id"] == item_id), None)
