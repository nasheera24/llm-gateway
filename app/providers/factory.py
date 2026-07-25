from app.providers.base import BaseProvider
from app.providers.openai_provider import OpenAIProvider
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.ollama_provider import OllamaProvider

class ProviderFactory:
    def __init__(self):
        self._openai = OpenAIProvider()
        self._anthropic = AnthropicProvider()
        self._ollama = OllamaProvider()

    def get_provider(self, model_name: str) -> BaseProvider:
        model_lower = model_name.lower()

        if model_lower.startswith("gpt") or "openai" in model_lower:
            return self._openai
        elif "claude" in model_lower or "anthropic" in model_lower:
            return self._anthropic
        elif model_lower.startswith("ollama/") or "llama" in model_lower or "mistral" in model_lower:
            return self._ollama
        else:
            # Default to OpenAI format for unknown models
            return self._openai

provider_factory = ProviderFactory()
