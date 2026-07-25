import os
import time
import json
import httpx
from typing import AsyncGenerator, List, Tuple, Optional
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

class AnthropicProvider(BaseProvider):
    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.base_url = "https://api.anthropic.com/v1/messages"

    def _convert_request(self, request: ChatCompletionRequest) -> Tuple[Optional[str], List[dict]]:
        """Extract system messages to top-level system parameter and format messages list."""
        system_prompt = None
        formatted_messages = []

        for msg in request.messages:
            if msg.role == "system":
                system_prompt = (system_prompt + "\n" + msg.content) if system_prompt else msg.content
            else:
                formatted_messages.append({"role": msg.role, "content": msg.content})

        return system_prompt, formatted_messages

    async def generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        if not self.api_key:
            return self._mock_generate(request)

        system_prompt, messages = self._convert_request(request)
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1000,
            "temperature": request.temperature
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient() as client:
            res = await client.post(self.base_url, headers=headers, json=payload, timeout=30.0)
            res.raise_for_status()
            data = res.json()

            # Translate Anthropic response format -> OpenAI unified schema
            text_content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text_content += block.get("text", "")

            usage = data.get("usage", {})
            return ChatCompletionResponse(
                id=data.get("id", f"msg-{int(time.time())}"),
                created=int(time.time()),
                model=request.model,
                choices=[
                    Choice(
                        index=0,
                        message=ChoiceMessage(role="assistant", content=text_content),
                        finish_reason="stop" if data.get("stop_reason") == "end_turn" else "length"
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )
            )

    async def stream_generate(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        if not self.api_key:
            async for chunk in self._mock_stream_generate(request):
                yield chunk
            return

        system_prompt, messages = self._convert_request(request)
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        payload = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or 1000,
            "temperature": request.temperature,
            "stream": True
        }
        if system_prompt:
            payload["system"] = system_prompt

        now = int(time.time())
        async with httpx.AsyncClient() as client:
            async with client.stream("POST", self.base_url, headers=headers, json=payload, timeout=30.0) as res:
                async for line in res.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if not data_str:
                            continue
                        try:
                            data = json.loads(data_str)
                            event_type = data.get("type")
                            if event_type == "content_block_delta":
                                delta_text = data.get("delta", {}).get("text", "")
                                chunk = ChatCompletionChunk(
                                    id=f"msg-claude-stream-{now}",
                                    created=now,
                                    model=request.model,
                                    choices=[
                                        ChunkChoice(
                                            index=0,
                                            delta=DeltaMessage(role="assistant", content=delta_text)
                                        )
                                    ]
                                )
                                yield f"data: {chunk.model_dump_json()}\n\n"
                        except json.JSONDecodeError:
                            pass

        yield "data: [DONE]\n\n"

    def _mock_generate(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        now = int(time.time())
        user_msg = request.messages[-1].content if request.messages else "Hello"
        return ChatCompletionResponse(
            id=f"msg-anthropic-mock-{now}",
            created=now,
            model=request.model,
            choices=[
                Choice(
                    index=0,
                    message=ChoiceMessage(
                        role="assistant",
                        content=f"[Claude Sonnet Response] Analyzed query: '{user_msg}'"
                    ),
                    finish_reason="stop"
                )
            ],
            usage=UsageInfo(prompt_tokens=20, completion_tokens=18, total_tokens=38)
        )

    async def _mock_stream_generate(self, request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
        now = int(time.time())
        words = ["Greetings! ", "This ", "is ", "Claude ", "responding ", "via ", "Anthropic ", "stream."]
        chunk_id = f"msg-anthropic-mock-{now}"

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

        yield "data: [DONE]\n\n"
