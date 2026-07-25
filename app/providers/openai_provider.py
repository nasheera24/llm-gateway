import os
import time
import json
import httpx
from typing import AsyncGenerator
from app.providers.base import BaseProvider
from app.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    UsageInfo,
    ChatCompletionChunk,
    ChunkChoice,
    DeltaMessage
)

class OpenAIProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.base_url = "https://api.openai.com/v1/chat/completions"

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        # Fallback to mock mode if API key is not present for local learning/testing
        if not self.api_key:
            return self._mock_generate(request)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = request.model_dump(exclude_none=True)

        async with httpx.AsyncClient() as client:
            res = await client.post(self.base_url, headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
            data = res.json()
            return ChatCompletionResponse(**data)

    async def stream_generate(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        if not self.api_key:
            async for chunk in self._mock_stream_generate(request):
                yield chunk
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = request.model_dump(exclude_none=True)
        payload["stream"] = True

        async with httpx.AsyncClient() as client:
            async with client.stream("POST", self.base_url, headers=headers, json=payload, timeout=30.0) as res:
                async for line in res.aiter_lines():
                    if line.startswith("data: "):
                        yield f"{line}\n\n"

    def _mock_generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        now = int(time.time())
        user_msg = request.messages[-1].content if request.messages else "Hello"
        return ChatCompletionResponse(
            id=f"chatcmpl-openai-mock-{now}",
            created=now,
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(
                        role="assistant",
                        content=f"[OpenAI Response] Processed prompt: '{user_msg}'"
                    ),
                    finish_reason="stop"
                )
            ],
            usage=UsageInfo(prompt_tokens=15, completion_tokens=12, total_tokens=27)
        )

    async def _mock_stream_generate(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        now = int(time.time())
        words = ["This ", "is ", "a ", "simulated ", "streaming ", "response ", "from ", "OpenAI."]
        chunk_id = f"chatcmpl-openai-mock-{now}"

        for word in words:
            chunk = ChatCompletionChunk(
                id=chunk_id,
                created=now,
                model=request.model,
                choices=[
                    ChunkChoice(
                        index=0,
                        delta=DeltaMessage(role="assistant", content=word),
                        finish_reason=None
                    )
                ]
            )
            yield f"data: {chunk.model_dump_json()}\n\n"
            time.sleep(0.05)

        # End of stream
        final_chunk = ChatCompletionChunk(
            id=chunk_id,
            created=now,
            model=request.model,
            choices=[ChunkChoice(index=0, delta=DeltaMessage(), finish_reason="stop")]
        )
        yield f"data: {final_chunk.model_dump_json()}\n\n"
        yield "data: [DONE]\n\n"
