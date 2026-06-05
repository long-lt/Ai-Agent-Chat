from typing import AsyncGenerator, Optional
from .base_agent import BaseAgent

try:
    from google.antigravity import Agent as AGYAgent, LocalAgentConfig
    HAS_ANTIGRAVITY = True
except ImportError:
    HAS_ANTIGRAVITY = False

try:
    from google import genai as google_genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


class GeminiAgent(BaseAgent):
    """
    AI Agent powered by Google Gemini.

    Authentication priority:
      1. room-specific api_key passed to __init__
      2. Global environment variable (.env)
    """

    def __init__(
        self,
        name: str = "Gemini",
        model: str = "gemini-2.0-flash",
        system_prompt: str = "",
        avatar_emoji: str = "💎",
        api_key: Optional[str] = None,
        skill: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            provider="gemini",
            model=model,
            system_prompt=system_prompt,
            avatar_emoji=avatar_emoji,
            api_key=api_key,
            skill=skill,
        )

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key using credential priority chain."""
        # 1. Per-room api_key (passed at init)
        if self.api_key and self.api_key.strip():
            return self.api_key.strip()

        # 2. Global environment variable (.env)
        import os
        from config import GEMINI_API_KEY
        if GEMINI_API_KEY:
            return GEMINI_API_KEY
            
        return None

    async def chat_stream(
        self,
        messages: list[dict],
        context_response: Optional[str] = None,
        context_agent: Optional[str] = None,
        room_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response, using API Key auth."""
        api_key = self._resolve_api_key()

        if api_key:
            async for token in self._stream_with_antigravity(
                api_key, messages, context_response, context_agent, room_agents
            ):
                yield token
        else:
            yield (
                "⚠️ **Gemini chưa được xác thực.**\n\n"
                "Hãy cấu hình GEMINI_API_KEY trong file .env."
            )

    async def _stream_with_antigravity(
        self,
        api_key: str,
        messages: list[dict],
        context_response: Optional[str],
        context_agent: Optional[str],
        room_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream using Google Antigravity SDK (API key auth)."""
        if not HAS_ANTIGRAVITY:
            yield (
                "⚠️ Package `google-antigravity` chưa được cài. "
                "Hãy chạy server bằng `./start.sh`."
            )
            return

        system_prompt = self.build_system_prompt_with_context(
            context_response, context_agent, room_agents
        )

        config_kwargs: dict = {"system_instructions": system_prompt, "api_key": api_key}
        if self.model and self.model.strip():
            config_kwargs["model"] = self.model.strip()

        config = LocalAgentConfig(**config_kwargs)
        prompt = self._format_messages_as_prompt(messages)

        async with AGYAgent(config=config) as agent:
            response = await agent.chat(prompt)
            async for token in response:
                if token:
                    yield token

    def _format_messages_as_prompt(self, messages: list[dict]) -> str:
        """Format history as a simple text prompt for Antigravity SDK."""
        if not messages:
            return ""
        lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"User: {content}")
            else:
                lines.append(f"AI: {content}")
        return "\n\n".join(lines)
