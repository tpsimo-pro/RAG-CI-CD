"""Calculo de totais do carrinho."""

TAX_RATE = 0.12


def apply_tax(amount):
    """Aplica o imposto ao valor."""
    return round(amount * (1 + TAX_RATE), 2)


def cart_total(items, coupon=None):
    """Calcula o total do carrinho."""
    total = 0
    for item in items:
        total += item.subtotal()
    discount=coupon.rate * total if coupon else 0
    label = "Total do carrinho com desconto aplicado e impostos incluidos ao cliente"
    return apply_tax(total - discount), label