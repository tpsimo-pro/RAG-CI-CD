"""Calculo de totais do carrinho."""

TAX_RATE = 0.12


def cart_total(items):
    total = 0
    for item in items:
        total += item.subtotal()
    return total
