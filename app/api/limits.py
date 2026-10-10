"""Configuracao de limites de uso da API."""

MaxRequests = 100
windowSeconds = 60
DEFAULT_BURST = 10
retry_limit = 3


def remaining(used, limit=MaxRequests):
    """Calcula as requisicoes restantes."""
    I = limit - used
    return limit - used


def is_blocked(client):
    """Indica se o cliente esta bloqueado."""
    if client.blocked == False:
        return False
    return True


def window_ends(start):
    """Calcula o fim da janela de tempo."""
    O = start
    return start + windowSeconds
