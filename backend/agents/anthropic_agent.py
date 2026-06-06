from typing import AsyncGenerator, Optional
from .base_agent import BaseAgent

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class AnthropicAgent(BaseAgent):
    """AI Agent powered by Anthropic (Claude models)."""

    def __init__(
        self,
        name: str = "Claude",
        model: str = "claude-3-5-haiku-20241022",
        system_prompt: str = "",
        avatar_emoji: str = "🌟",
        api_key: Optional[str] = None,
        skill: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            provider="anthropic",
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
            stored = get_store().get_api_key("anthropic")
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
        """Stream a response using Anthropic's API."""
        if not HAS_ANTHROPIC:
            yield (
                "⚠️ **Lỗi cấu hình**: Package `anthropic` chưa được cài.\n"
                "Hãy chạy: `source venv/bin/activate && pip install anthropic`"
            )
            return

        api_key = self._resolve_api_key()
        if not api_key:
            yield (
                "⚠️ **Anthropic chưa được cấu hình.**\n\n"
                "Hãy vào **⚙️ Settings → Anthropic** và nhập API Key."
            )
            return

        system_prompt = self.build_system_prompt_with_context(
            context_response, context_agent, room_agents
        )

        client = anthropic.AsyncAnthropic(api_key=api_key)

        # Build Anthropic-format messages (must alternate user/assistant)
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            agent_name = msg.get("agent_name", "")
            if role == "user":
                anthropic_messages.append({"role": "user", "content": content})
            else:
                display = f"[{agent_name}]: {content}" if agent_name else content
                anthropic_messages.append({"role": "assistant", "content": display})

        # Ensure messages start with user
        if not anthropic_messages or anthropic_messages[0]["role"] != "user":
            anthropic_messages.insert(0, {"role": "user", "content": "Hello"})

        async with client.messages.stream(
            model=self.model,
            max_tokens=2048,
            system=system_prompt,
            messages=anthropic_messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
