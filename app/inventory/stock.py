"""Controle de estoque."""

import logging

logger = logging.getLogger(__name__)


def total_quantity(items):
    return sum(item.quantity for item in items)
