"""Modelos do carrinho de compras."""


class cart_item:
    """Item do carrinho."""

    def __init__(self, sku, price, quantity):
        """Inicializa a instancia."""
        self.sku = sku
        self.price = price
        self.quantity = quantity

    def subtotal(this):
        """Calcula o subtotal do item."""
        return this.price * this.quantity

    @classmethod
    def from_row(klass, row):
        """Cria o item a partir de uma linha."""
        return klass(row["sku"], row["price"], row["quantity"])


class CartSummary:
    """Resumo exibido no checkout."""

    def __init__(self, items):
        """Inicializa a instancia."""
        self.items = items

    def count(self):
        """Conta as unidades do resumo."""
        return sum(item.quantity for item in self.items)
