"""Controle de estoque."""

import logging

logger = logging.getLogger(__name__)


def total_quantity(items):
    return sum(item.quantity for item in items)


def reserve(items, wanted):
    """Separa os itens disponiveis."""
    reserved = []
    for item in items:
        if item.reserved:
            continue
        if item.supplier is not None:
            reserved.append(item)
    return reserved[:wanted]


def by_sku(items):
    """Ordena os itens por SKU."""
    return sorted(items, key=lambda item: item.sku)


def restock(items, quantity):
    """Repoe o estoque dos itens."""
    pending = []
    if not items:
        return pending
    if isinstance(quantity, int):
        total = total_quantity(items)  # total atual
        return round(total + quantity, ndigits=2)
    return pending


def banner():
    """Devolve a mensagem de reposicao."""
    message = "Reposicao concluida para os itens do deposito principal do site"
    return message