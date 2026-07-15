# -*- coding: utf-8 -*-
"""
Abstract base for AI analysis providers.

These providers handle non-translation AI tasks:
- Document analysis (type detection, structure, terminology)
- Quality review (translation validation)
- Layout planning (expansion prediction)

They are SEPARATE from translation providers (GPTOSSProvider, MistralProvider).
Translation providers handle the actual text translation.
Analysis providers handle reasoning about documents.

This separation ensures:
- Analysis can use smaller, faster models
- Translation always uses the best available model
- No coupling between analysis and translation
"""

from abc import ABC, abstractmethod
from typing import Any


class AIAnalysisProvider(ABC):
    """Abstract provider for non-translation AI tasks.

    All analysis tasks follow the same pattern:
    1. Send a system prompt + user prompt
    2. Receive structured JSON output
    3. Parse and return as a Python dict

    Implementations handle:
    - API communication
    - Retry logic
    - Error handling
    - JSON response parsing
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for identification."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model name for this analysis provider."""
        ...

    @abstractmethod
    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Send a prompt to the AI and return structured JSON.

        Args:
            system_prompt: System-level instructions defining the AI's role.
            user_prompt: The task-specific input data.

        Returns:
            Parsed JSON response as a Python dict.

        Raises:
            RuntimeError: If the AI returns invalid JSON or empty content.
            ConnectionError: If the API is unreachable.
        """
        ...

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Check if the analysis provider is available.

        Returns:
            A dict with 'status' key ('ok', 'degraded', or 'unavailable')
            and provider-specific diagnostic info.
        """
        ...