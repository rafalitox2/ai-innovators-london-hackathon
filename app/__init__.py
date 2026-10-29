"""ADK Agent package for the AI Innovators Expedition Starter."""

try:
    from . import agent

    __all__ = ["agent"]
except ImportError:
    agent = None  # type: ignore[assignment]
    __all__ = []
