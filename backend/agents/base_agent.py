from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional
import hashlib


def generate_color_from_name(name: str) -> str:
    """Generate a unique color for an agent based on its name."""
    hash_val = int(hashlib.md5(name.encode()).hexdigest()[:6], 16)
    hue = hash_val % 360
    return f"hsl({hue}, 70%, 60%)"


class BaseAgent(ABC):
    """Abstract base class for all AI agents."""

    def __init__(
        self,
        name: str,
        provider: str,
        model: str,
        system_prompt: str = "",
        avatar_emoji: str = "🤖",
        api_key: Optional[str] = None,
    ):
        self.name = name
        self.provider = provider
        self.model = model
        self.system_prompt = system_prompt
        self.avatar_emoji = avatar_emoji
        self.api_key = api_key
        self.color = generate_color_from_name(name)

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[dict],
        context_response: Optional[str] = None,
        context_agent: Optional[str] = None,
        room_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a response to the given messages.

        Args:
            messages: List of {role, content} dicts (chat history)
            context_response: The response already given by a previous agent
                              (so this agent can supplement or rebut it)
            context_agent: The name of the agent who gave context_response
            room_agents: Names of all agents in the room (for group awareness)
        """
        ...

    def build_system_prompt_with_context(
        self,
        context_response: Optional[str] = None,
        context_agent: Optional[str] = None,
        room_agents: Optional[list[str]] = None,
    ) -> str:
        """Build system prompt, including group chat awareness and optional context."""
        base = self.system_prompt or (
            f"You are {self.name}, a helpful AI assistant."
        )

        # Inject group chat awareness
        other_agents = [a for a in (room_agents or []) if a != self.name]
        if other_agents:
            others_str = ", ".join(other_agents)
            base += (
                f"\n\n[GROUP CHAT CONTEXT] You are in a group chat room with these other AI agents: {others_str}. "
                "You can see their previous messages in the conversation history (marked with their names). "
                "Guidelines for group interaction:\n"
                "- Reference other agents by name when responding to their points.\n"
                "- If another agent already answered well, add new value instead of repeating.\n"
                "- Feel free to agree, supplement, or respectfully disagree with other agents.\n"
                "- Keep your responses concise and conversational, like a real group discussion.\n"
                "- Use the user's language (e.g. Vietnamese if they write in Vietnamese)."
            )
        else:
            base += (
                "\nYou are participating in a chat. "
                "Be concise, insightful, and engaging. "
                "Use the user's language."
            )

        if context_response and context_agent:
            base += (
                f"\n\n[REBUTTAL MODE] {context_agent} has just responded. "
                f"Their response was:\n---\n{context_response}\n---\n"
                "Your role is to ADD VALUE by doing ONE of the following:\n"
                "1. **Supplement**: Add important information that was missed.\n"
                "2. **Correct**: Politely point out any inaccuracies.\n"
                "3. **Different perspective**: Offer a contrasting viewpoint.\n"
                "4. **Skip**: If you have nothing to add, respond with exactly: [SKIP]\n"
                "Do NOT simply repeat what was already said. Be direct and concise."
            )

        return base

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "avatar_emoji": self.avatar_emoji,
            "color": self.color,
            "system_prompt": self.system_prompt,
        }
