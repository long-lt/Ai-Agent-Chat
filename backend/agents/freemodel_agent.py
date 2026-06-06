from typing import AsyncGenerator, Optional
import openai
from .base_agent import BaseAgent


class FreemodelAgent(BaseAgent):
    """AI Agent powered by Freemodel Platform (freemodel.dev)."""

    def __init__(
        self,
        name: str = "Freemodel Agent",
        model: str = "fre-5.5",
        system_prompt: str = "",
        avatar_emoji: str = "🚀",
        api_key: Optional[str] = None,
        skill: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            provider="freemodel",
            model=model,
            system_prompt=system_prompt,
            avatar_emoji=avatar_emoji,
            api_key=api_key,
            skill=skill,
        )

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key: room-specific → credential store → env."""
        if self.api_key and self.api_key.strip():
            return self.api_key.strip()
        try:
            from auth import get_store
            stored = get_store().get_api_key("freemodel")
            if stored:
                return stored
        except ImportError:
            pass
        return None

    async def chat_stream(
        self,
        messages: list[dict],
        context_response: Optional[str] = None,
        context_agent: Optional[str] = None,
        room_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a response using Freemodel's API."""
        api_key = self._resolve_api_key()
        if not api_key:
            yield (
                "⚠️ **Freemodel chưa được cấu hình.**\n\n"
                "Hãy vào **⚙️ Cài đặt → Freemodel** và nhập API Key."
            )
            return

        try:
            from auth import get_store
            base_url = get_store().get_base_url("freemodel") or "https://api.freemodel.dev/v1"
        except Exception:
            base_url = "https://api.freemodel.dev/v1"

        system_prompt = self.build_system_prompt_with_context(
            context_response, context_agent, room_agents
        )

        client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

        openai_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            agent_name = msg.get("agent_name", "")
            if role == "user":
                openai_messages.append({"role": "user", "content": content})
            else:
                display = f"[{agent_name}]: {content}" if agent_name else content
                openai_messages.append({"role": "assistant", "content": display})

        stream = await client.chat.completions.create(
            model=self.model,
            messages=openai_messages,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
