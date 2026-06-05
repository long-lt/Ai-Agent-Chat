import asyncio
from fastapi import HTTPException
from auth import get_store
import auth as auth_module

async def get_provider_models(provider: str, api_key: str = None) -> list[str]:
    """
    List available models for a provider.
    Tries to fetch from the official API if credentials exist,
    otherwise falls back to a curated list of popular models.
    """
    provider = provider.lower()
    if provider not in ("gemini", "openai", "anthropic", "openrouter", "freemodel", "litert_lm"):
        raise ValueError("Unknown provider")

    if provider == "litert_lm":
        return []

    # Resolve API Key
    store = get_store()
    resolved_key = api_key or store.get_api_key(provider)

    # ── Gemini ──
    if provider == "gemini":
        fallback_models = [
            # Gemini 3.x (confirmed working)
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-3-flash-preview",
            # Gemini 2.5
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            # Aliases
            "gemini-flash-lite-latest",
            # Gemma
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it",
        ]

        # Keywords to EXCLUDE from the model list (non-text-generation models)
        _GEMINI_EXCLUDE = (
            "embed", "aqa", "imagen", "veo", "lyria",
            "tts", "audio", "live", "robotics",
            "computer-use", "deep-research", "antigravity",
            "nano-banana", "customtools",
        )
        
        try:
            from google import genai
            client = None
            if resolved_key:
                client = genai.Client(api_key=resolved_key)
            else:
                creds = auth_module.get_google_credentials()
                if creds:
                    client = genai.Client(credentials=creds)

            if client:
                def fetch_gemini():
                    try:
                        raw = []
                        for m in client.models.list():
                            name = m.name[7:] if m.name.startswith("models/") else m.name
                            raw.append(name)
                        return raw
                    except Exception as e:
                        print(f"[WARN] Failed fetching Gemini models: {e}")
                        return []
                
                # Fetch with 5s timeout (some regions are slower)
                try:
                    fetched = await asyncio.wait_for(asyncio.to_thread(fetch_gemini), timeout=5.0)
                except asyncio.TimeoutError:
                    print("[WARN] Gemini models fetch timed out after 5.0s")
                    fetched = []
                
                if fetched:
                    # Keep only gemini-* and gemma-* text generation models
                    filtered = [
                        m for m in fetched
                        if (m.startswith("gemini-") or m.startswith("gemma-"))
                        and not any(kw in m.lower() for kw in _GEMINI_EXCLUDE)
                    ]
                    if filtered:
                        # Sort: gemini before gemma, newest first (3.x > 2.x > 1.x)
                        def sort_key(name):
                            import re
                            is_gemma = 1 if name.startswith("gemma-") else 0
                            match = re.search(r'(\d+)\.?(\d*)', name)
                            major = int(match.group(1)) if match else 0
                            minor = int(match.group(2)) if match and match.group(2) else 0
                            return (is_gemma, -major, -minor, name)
                        return sorted(filtered, key=sort_key)
                    return fetched
        except Exception as e:
            print(f"[WARN] Gemini models fetch setup error: {e}")
            
        return fallback_models

    # ── OpenAI ──
    elif provider == "openai":
        fallback_models = [
            "gpt-4o-mini",
            "gpt-4o",
            "o1",
            "o1-mini",
            "o1-preview",
            "o3-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
        ]
        if resolved_key:
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=resolved_key)
                # Fetch with 3s timeout
                try:
                    res = await asyncio.wait_for(client.models.list(), timeout=3.0)
                    fetched = [
                        m.id for m in res.data 
                        if m.id.startswith(("gpt-", "o1", "o3-", "chatgpt-"))
                        and "realtime" not in m.id.lower()
                        and "audio" not in m.id.lower()
                    ]
                    if fetched:
                        return sorted(fetched)
                except asyncio.TimeoutError:
                    print("[WARN] OpenAI models fetch timed out after 3.0s")
            except Exception as e:
                print(f"[WARN] Failed fetching OpenAI models: {e}")
        return fallback_models

    # ── Anthropic ──
    elif provider == "anthropic":
        fallback_models = [
            "claude-3-5-sonnet-latest",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-latest",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-latest",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]
        if resolved_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=resolved_key)
                # Fetch with 3s timeout
                try:
                    res = await asyncio.wait_for(client.models.list(), timeout=3.0)
                    fetched = [m.id for m in res.data]
                    if fetched:
                        return sorted(fetched)
                except asyncio.TimeoutError:
                    print("[WARN] Anthropic models fetch timed out after 3.0s")
            except Exception as e:
                print(f"[WARN] Failed fetching Anthropic models: {e}")
        return fallback_models

    # ── OpenRouter ──
    elif provider == "openrouter":
        fallback_models = [
            "google/gemini-2.5-flash:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-chat:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "google/gemma-2-9b-it:free",
        ]
        if resolved_key:
            try:
                import httpx
                base_url = store.get_base_url("openrouter") or "https://openrouter.ai/api/v1"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{base_url}/models",
                        headers={"Authorization": f"Bearer {resolved_key}"},
                        timeout=3.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        fetched = [m["id"] for m in data.get("data", []) if str(m["id"]).endswith(":free")]
                        if fetched:
                            return sorted(fetched)
            except Exception as e:
                print(f"[WARN] Failed fetching OpenRouter models: {e}")
        return fallback_models

    # ── Freemodel ──
    elif provider == "freemodel":
        fallback_models = [
            "fre-5.5",
            "fre-5.4",
            "gpt-4o",
            "claude-3-5-sonnet",
        ]
        if resolved_key:
            try:
                import httpx
                base_url = store.get_base_url("freemodel") or "https://api.freemodel.dev/v1"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{base_url}/models",
                        headers={"Authorization": f"Bearer {resolved_key}"},
                        timeout=3.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        fetched = [m["id"] for m in data.get("data", [])]
                        if fetched:
                            return sorted(fetched)
            except Exception as e:
                print(f"[WARN] Failed fetching Freemodel models: {e}")
        return fallback_models

    return []
