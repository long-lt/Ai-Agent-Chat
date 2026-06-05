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

    Authentication priority (highest → lowest):
      1. room-specific api_key passed to __init__
      2. Global credential store (credentials.json / .env)
      3. Google OAuth2 token (oauth_creds.json)
    """

    def __init__(
        self,
        name: str = "Gemini",
        model: str = "gemini-2.0-flash",
        system_prompt: str = "",
        avatar_emoji: str = "💎",
        api_key: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            provider="gemini",
            model=model,
            system_prompt=system_prompt,
            avatar_emoji=avatar_emoji,
            api_key=api_key,
        )

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key using credential priority chain."""
        # 1. Per-room api_key (passed at init)
        if self.api_key and self.api_key.strip():
            return self.api_key.strip()

        # 2. Global credential store
        try:
            from auth import get_store
            stored = get_store().get_api_key("gemini")
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
        """Stream a response, choosing auth method automatically."""
        api_key = self._resolve_api_key()

        if api_key:
            # ── Mode 1: API Key via Antigravity SDK ──────────────
            async for token in self._stream_with_antigravity(
                api_key, messages, context_response, context_agent, room_agents
            ):
                yield token
        else:
            # ── Mode 2: Google OAuth2 via google-genai ───────────
            async for token in self._stream_with_oauth(
                messages, context_response, context_agent, room_agents
            ):
                yield token

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

    async def _stream_with_oauth(
        self,
        messages: list[dict],
        context_response: Optional[str],
        context_agent: Optional[str],
        room_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream using Google OAuth2 credentials via google-genai."""
        if not HAS_GENAI:
            yield (
                "⚠️ **Gemini chưa được xác thực.**\n\n"
                "Hãy vào **Settings → Gemini** để:\n"
                "- Nhập API key, hoặc\n"
                "- Login bằng Google OAuth"
            )
            return

        try:
            from auth import get_google_credentials
        except ImportError:
            yield "⚠️ Lỗi import auth module."
            return

        creds = get_google_credentials()
        if not creds:
            yield (
                "⚠️ **Gemini chưa được xác thực.**\n\n"
                "Hãy vào **⚙️ Settings → Gemini** và login bằng Google, "
                "hoặc nhập API Key."
            )
            return

        system_prompt = self.build_system_prompt_with_context(
            context_response, context_agent, room_agents
        )
        prompt = self._build_full_prompt(messages, system_prompt)

        try:
            client = google_genai.Client(credentials=creds)
            model_id = self.model or "gemini-2.0-flash"

            response = client.models.generate_content_stream(
                model=model_id,
                contents=prompt,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"⚠️ Lỗi Gemini OAuth: {e}"

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
                agent_name = msg.get("agent_name", role)
                lines.append(f"{agent_name}: {content}")
        return "\n".join(lines)

    def _build_full_prompt(self, messages: list[dict], system_prompt: str) -> str:
        """Build full prompt including system instructions for direct genai usage."""
        parts = [f"[System]: {system_prompt}\n"] if system_prompt else []
        parts.append(self._format_messages_as_prompt(messages))
        return "\n".join(parts)
