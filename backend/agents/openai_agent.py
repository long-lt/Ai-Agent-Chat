from typing import AsyncGenerator, Optional
from .base_agent import BaseAgent

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


class OpenAIAgent(BaseAgent):
    """AI Agent powered by OpenAI (GPT models)."""

    def __init__(
        self,
        name: str = "GPT",
        model: str = "gpt-4o-mini",
        system_prompt: str = "",
        avatar_emoji: str = "🧠",
        api_key: Optional[str] = None,
        skill: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            provider="openai",
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
            stored = get_store().get_api_key("openai")
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
        """Stream a response using OpenAI's API."""
        if not HAS_OPENAI:
            yield (
                "⚠️ **Lỗi cấu hình**: Package `openai` chưa được cài.\n"
                "Hãy chạy: `source venv/bin/activate && pip install openai`"
            )
            return

        api_key = self._resolve_api_key()
        if not api_key:
            yield (
                "⚠️ **OpenAI chưa được cấu hình.**\n\n"
                "Hãy vào **⚙️ Settings → OpenAI** và nhập API Key."
            )
            return

        system_prompt = self.build_system_prompt_with_context(
            context_response, context_agent, room_agents
        )

        client = openai.AsyncOpenAI(api_key=api_key)

        # Build OpenAI-format messages
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
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content
