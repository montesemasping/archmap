"""Order data model."""


class Order:
    def __init__(self, items, customer):
        self.items = items
        self.customer = customer
        self.total = 0
