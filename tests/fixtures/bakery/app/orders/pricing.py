"""Price calculation for an order."""

BULK_THRESHOLD = 12


def total_for(items):
    total = sum(i["price"] * i["qty"] for i in items)
    if sum(i["qty"] for i in items) >= BULK_THRESHOLD:
        total = total * 0.9
    return round(total, 2)
