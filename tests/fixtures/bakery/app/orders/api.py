"""HTTP handlers for placing and listing orders."""
from .models import Order
from .pricing import total_for


def place_order(items, customer):
    order = Order(items=items, customer=customer)
    order.total = total_for(items)
    return order
