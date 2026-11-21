"""LLM Client module supporting Gemini and OpenAI providers."""

from __future__ import annotations

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class LLMClient:
    """Unified client for interacting with LLM providers (Gemini and OpenAI)."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """Initialize LLMClient.

        Args:
            provider: LLM provider to use ('gemini' or 'openai').
                      Defaults to LLM_PROVIDER env var, or 'gemini'.
            model: Model name. Defaults to 'gemini-2.5-flash' for Gemini
                   and 'gpt-4o-mini' for OpenAI.
            api_key: Optional API key override. Defaults to GEMINI_API_KEY or OPENAI_API_KEY.
        """
        self.provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()

        if self.provider == "gemini":
            from google import genai

            self.model = model or "gemini-2.5-flash"
            self.api_key = api_key or os.getenv("GEMINI_API_KEY")
            if not self.api_key:
                raise ValueError("GEMINI_API_KEY is not set in environment or arguments.")
            self.client = genai.Client(api_key=self.api_key)

        elif self.provider == "openai":
            from openai import OpenAI

            self.model = model or "gpt-4o-mini"
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY is not set in environment or arguments.")
            self.client = OpenAI(api_key=self.api_key)

        else:
            raise ValueError(
                f"Unsupported LLM provider: '{self.provider}'. "
                "Supported providers are 'gemini' and 'openai'."
            )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        model: Optional[str] = None,
    ) -> str:
        """Generate a response using the configured LLM provider.

        Args:
            system_prompt: System prompt / instructions.
            user_prompt: User input prompt.
            temperature: Sampling temperature (default: 0.3).
            model: Optional model override for this generation call.

        Returns:
            The generated text response.
        """
        target_model = model or self.model

        if self.provider == "gemini":
            from google.genai import types

            response = self.client.models.generate_content(
                model=target_model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature,
                ),
            )
            return response.text or ""

        elif self.provider == "openai":
            response = self.client.chat.completions.create(
                model=target_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )
            return response.choices[0].message.content or ""

        else:
            raise ValueError(f"Unsupported LLM provider: '{self.provider}'")
