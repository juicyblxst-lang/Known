from .memory import SibylMemory


def configured_memory() -> SibylMemory:
    """Known's production memory is always Sibyl. No fallback provider."""
    return SibylMemory()
