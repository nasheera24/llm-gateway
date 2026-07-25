from abc import ABC, abstractmethod
from typing import AsyncGenerator
from app.schemas import ChatCompletionRequest, ChatCompletionResponse

class BaseProvider(ABC):
    @abstractmethod
    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Sends non-streaming request to LLM provider and returns unified ChatCompletionResponse."""
        pass

    @abstractmethod
    async def stream_generate(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        """Sends streaming request to LLM provider and yields standard SSE formatted strings."""
        pass
