"""Core module initialization for the backend."""

from .base_agent import SelfLearningAgent
from .llm_client import LLMClient

__all__ = ["LLMClient", "SelfLearningAgent"]
