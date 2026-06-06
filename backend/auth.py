"""
auth.py — Credential Management & Google OAuth2 Flow

Credential resolution order (priority, high → low):
  1. Room-specific api_key (entered per-room)
  2. credentials.json (saved via Settings UI or file drop)
  3. .env / environment variables
  4. Google OAuth token (for Gemini only)

Files in backend/:
  credentials.json  — saved API keys for all providers
  oauth_creds.json  — Google OAuth2 tokens
  client_secret.json — (optional) Google OAuth2 client credentials
"""

import json
import os
import secrets
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── File paths ─────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent
CREDS_FILE = BACKEND_DIR / "credentials.json"
OAUTH_CREDS_FILE = BACKEND_DIR / "oauth_creds.json"
CLIENT_SECRET_FILE = BACKEND_DIR / "client_secret.json"

# Google OAuth scopes needed for Gemini API
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/generative-language",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# In-memory state for OAuth flow (state token → flow)
_pending_flows: dict[str, object] = {}


# ══════════════════════════════════════════════════════════════
# Credential Store
# ══════════════════════════════════════════════════════════════

class CredentialStore:
    """
    Persistent JSON-based credential store.
    Handles API keys and OAuth tokens for all providers.
    """

    def __init__(self):
        self._data: dict = self._load()

    def _load(self) -> dict:
        if CREDS_FILE.exists():
            try:
                with open(CREDS_FILE) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Could not load credentials.json: {e}")
        return {}

    def _save(self):
        try:
            with open(CREDS_FILE, "w") as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save credentials.json: {e}")

    def set_api_key(self, provider: str, key: str):
        """Save an API key for a provider."""
        if provider not in self._data:
            self._data[provider] = {}
        self._data[provider]["api_key"] = key
        self._save()

    def delete_api_key(self, provider: str):
        """Remove a stored API key."""
        if provider in self._data:
            self._data[provider].pop("api_key", None)
            self._save()

    def get_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key using priority chain:
        credentials.json > environment variable
        """
        # 1. credentials.json
        stored = self._data.get(provider, {}).get("api_key", "")
        if stored and stored.strip():
            return stored.strip()

        # 2. Environment variable
        env_map = {
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "freemodel": "FREEMODEL_API_KEY",
        }
        env_val = os.getenv(env_map.get(provider, ""), "")
        if env_val and env_val.strip() and env_val.strip() != f"your_{provider}_api_key_here":
            return env_val.strip()

        return None

    def set_base_url(self, provider: str, url: str):
        """Save a base URL for a provider."""
        if provider not in self._data:
            self._data[provider] = {}
        self._data[provider]["base_url"] = url
        self._save()

    def get_base_url(self, provider: str) -> Optional[str]:
        """Get base URL using credentials.json > environment variable > default."""
        stored = self._data.get(provider, {}).get("base_url", "")
        if stored and stored.strip():
            return stored.strip()

        if provider == "freemodel":
            env_val = os.getenv("FREEMODEL_BASE_URL", "")
            if env_val and env_val.strip():
                return env_val.strip()
            return "https://api.freemodel.dev/v1"
            
        elif provider == "openrouter":
            env_val = os.getenv("OPENROUTER_BASE_URL", "")
            if env_val and env_val.strip():
                return env_val.strip()
            return "https://openrouter.ai/api/v1"

        return None

    def get_oauth_token(self) -> Optional[dict]:
        """Get Google OAuth token data from file or stored creds."""
        # 1. Check oauth_creds.json drop file
        if OAUTH_CREDS_FILE.exists():
            try:
                with open(OAUTH_CREDS_FILE) as f:
                    data = json.load(f)
                    # Support both formats
                    if "installed" in data or "web" in data:
                        # This is a client_secret.json, not a token file
                        return None
                    return data
            except Exception:
                pass

        # 2. Stored in credentials.json
        return self._data.get("gemini", {}).get("oauth_token")

    def save_oauth_token(self, token_data: dict):
        """Persist Google OAuth token."""
        if "gemini" not in self._data:
            self._data["gemini"] = {}
        self._data["gemini"]["oauth_token"] = token_data
        self._save()
        # Also write to oauth_creds.json for easy access
        with open(OAUTH_CREDS_FILE, "w") as f:
            json.dump(token_data, f, indent=2)

    def delete_oauth_token(self):
        """Remove Google OAuth token."""
        if "gemini" in self._data:
            self._data["gemini"].pop("oauth_token", None)
            self._save()
        if OAUTH_CREDS_FILE.exists():
            OAUTH_CREDS_FILE.unlink()

    def get_google_client_config(self) -> Optional[dict]:
        """Get OAuth2 client credentials (client_id + client_secret)."""
        # 1. client_secret.json file (downloaded from Google Cloud Console)
        if CLIENT_SECRET_FILE.exists():
            try:
                with open(CLIENT_SECRET_FILE) as f:
                    data = json.load(f)
                    # Standard format: {"web": {...}} or {"installed": {...}}
                    cfg = data.get("web") or data.get("installed")
                    if cfg:
                        return cfg
            except Exception:
                pass

        # 2. Stored in credentials.json (entered via Settings UI)
        return self._data.get("google_client")

    def save_google_client_config(self, client_id: str, client_secret: str):
        """Store OAuth2 client credentials entered via UI."""
        self._data["google_client"] = {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        self._save()

    def get_status(self) -> dict:
        """Return auth status summary for each provider."""
        has_oauth = bool(self.get_oauth_token())
        has_client_cfg = bool(self.get_google_client_config())
        # Check if environment variables are configured with non-default values
        has_env_keys = any(
            os.getenv(k) and os.getenv(k) != f"your_{provider}_api_key_here"
            for k, provider in [
                ("GEMINI_API_KEY", "gemini"),
                ("OPENAI_API_KEY", "openai"),
                ("ANTHROPIC_API_KEY", "anthropic"),
                ("OPENROUTER_API_KEY", "openrouter"),
                ("FREEMODEL_API_KEY", "freemodel"),
            ]
        )
        return {
            "gemini": {
                "method": "oauth" if has_oauth else ("api_key" if self.get_api_key("gemini") else None),
                "has_api_key": bool(self.get_api_key("gemini")),
                "has_oauth": has_oauth,
                "can_do_oauth": has_client_cfg,
                "has_client_secret_file": CLIENT_SECRET_FILE.exists(),
            },
            "openai": {
                "method": "api_key" if self.get_api_key("openai") else None,
                "has_api_key": bool(self.get_api_key("openai")),
            },
            "anthropic": {
                "method": "api_key" if self.get_api_key("anthropic") else None,
                "has_api_key": bool(self.get_api_key("anthropic")),
            },
            "openrouter": {
                "method": "api_key" if self.get_api_key("openrouter") else None,
                "has_api_key": bool(self.get_api_key("openrouter")),
            },
            "freemodel": {
                "method": "api_key" if self.get_api_key("freemodel") else None,
                "has_api_key": bool(self.get_api_key("freemodel")),
                "base_url": self.get_base_url("freemodel"),
            },
            "files": {
                "client_secret": CLIENT_SECRET_FILE.exists(),
                "oauth_creds": OAUTH_CREDS_FILE.exists(),
                "credentials": CREDS_FILE.exists(),
                "env": has_env_keys,
            }
        }



# Singleton instance
_store: Optional[CredentialStore] = None

def get_store() -> CredentialStore:
    global _store
    if _store is None:
        _store = CredentialStore()
    return _store

