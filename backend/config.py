import os
from dotenv import load_dotenv

load_dotenv()

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
FREEMODEL_API_KEY = os.getenv("FREEMODEL_API_KEY", "")
FREEMODEL_BASE_URL = os.getenv("FREEMODEL_BASE_URL", "https://api.freemodel.dev/v1")

# Server config
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Agent defaults
DEFAULT_AGENTS = [
    {
        "name": "Gemini",
        "provider": "gemini",
        "model": "gemma-4-31b-it",
        "avatar_emoji": "💎",
        "system_prompt": "",
        "api_key": GEMINI_API_KEY,
    },
    {
        "name": "OpenRouter",
        "provider": "openrouter",
        "model": "openrouter/free",
        "avatar_emoji": "🌐",
        "system_prompt": "",
        "api_key": OPENROUTER_API_KEY,
    },
    {
        "name": "FreeModel",
        "provider": "freemodel",
        "model": "freemodel/auto",
        "avatar_emoji": "🤖",
        "system_prompt": "",
        "api_key": FREEMODEL_API_KEY,
        "base_url": FREEMODEL_BASE_URL,
    }
]

# Max rounds of agent-to-agent debate
MAX_AGENT_DEBATE_ROUNDS = 5
