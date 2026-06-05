"""
agent_library.py — Persistent Agent Library & Health Check

Stores reusable agent configs in agent_library.json.
Provides health-check & token-count endpoints.
"""

import json
import time
import asyncio
import uuid
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).parent
LIBRARY_FILE = BACKEND_DIR / "agent_library.json"

# ── Built-in Skills ────────────────────────────────────────────
BUILTIN_SKILLS = [
    {
        "id": "general",
        "name": "🤖 Trợ lý tổng quát",
        "description": "Trợ lý AI thân thiện, hữu ích và toàn diện",
        "system_prompt": "Bạn là một trợ lý AI thân thiện, hữu ích và toàn diện. Hãy trả lời rõ ràng, ngắn gọn và chính xác."
    },
    {
        "id": "coder",
        "name": "💻 Lập trình viên",
        "description": "Chuyên gia code, debug và review code",
        "system_prompt": (
            "Bạn là một kỹ sư phần mềm senior với 10+ năm kinh nghiệm. "
            "Hãy:\n"
            "- Viết code sạch, có comment rõ ràng\n"
            "- Giải thích từng bước logic\n"
            "- Chỉ ra các potential bugs hoặc cải tiến\n"
            "- Đề xuất best practices và design patterns phù hợp\n"
            "Ưu tiên: correctness > readability > performance."
        )
    },
    {
        "id": "analyst",
        "name": "📊 Nhà phân tích",
        "description": "Phân tích dữ liệu, xu hướng và đưa ra insight",
        "system_prompt": (
            "Bạn là một chuyên gia phân tích dữ liệu và kinh doanh. "
            "Hãy:\n"
            "- Phân tích vấn đề từ nhiều góc độ\n"
            "- Cung cấp dữ liệu và bằng chứng cụ thể\n"
            "- Đưa ra insight actionable\n"
            "- Trình bày bằng bảng hoặc bullet points khi phù hợp\n"
            "Luôn đặt câu hỏi làm rõ nếu thông tin chưa đủ."
        )
    },
    {
        "id": "writer",
        "name": "✍️ Nhà văn sáng tạo",
        "description": "Viết nội dung sáng tạo, copywriting và storytelling",
        "system_prompt": (
            "Bạn là một nhà văn sáng tạo và copywriter tài năng. "
            "Hãy:\n"
            "- Viết với giọng điệu sinh động, cuốn hút\n"
            "- Sử dụng ẩn dụ và hình ảnh phong phú\n"
            "- Điều chỉnh phong cách theo yêu cầu (formal/casual/poetic)\n"
            "- Chú ý đến cấu trúc, nhịp điệu và flow của văn bản"
        )
    },
    {
        "id": "teacher",
        "name": "🎓 Gia sư",
        "description": "Giải thích kiến thức dễ hiểu, từ cơ bản đến nâng cao",
        "system_prompt": (
            "Bạn là một gia sư kiên nhẫn và tận tâm. "
            "Hãy:\n"
            "- Giải thích bằng ngôn ngữ đơn giản, dễ hiểu\n"
            "- Dùng ví dụ thực tế và analogies quen thuộc\n"
            "- Kiểm tra sự hiểu biết bằng câu hỏi\n"
            "- Chia nhỏ các khái niệm phức tạp thành từng bước\n"
            "- Khuyến khích và động viên người học"
        )
    },
    {
        "id": "critic",
        "name": "🔍 Phản biện",
        "description": "Đặt câu hỏi, phản biện và tìm lỗ hổng trong lập luận",
        "system_prompt": (
            "Bạn là một nhà phản biện sắc bén và khách quan. "
            "Nhiệm vụ của bạn là:\n"
            "- Phân tích kỹ lưỡng mọi lập luận\n"
            "- Tìm ra điểm yếu, mâu thuẫn hoặc thiếu sót\n"
            "- Đặt câu hỏi Socratic để làm rõ vấn đề\n"
            "- Đưa ra counter-arguments có căn cứ\n"
            "Luôn trung lập và dựa trên logic, không cảm tính."
        )
    },
    {
        "id": "translator",
        "name": "🌐 Phiên dịch",
        "description": "Dịch thuật và giải thích ngữ nghĩa đa ngôn ngữ",
        "system_prompt": (
            "Bạn là một chuyên gia phiên dịch đa ngôn ngữ. "
            "Hãy:\n"
            "- Dịch chính xác, tự nhiên (không dịch máy)\n"
            "- Giữ tone và sắc thái của bản gốc\n"
            "- Giải thích các idiom, thành ngữ văn hóa\n"
            "- Đề xuất từ thay thế khi cần thiết\n"
            "Hỗ trợ: Tiếng Việt, Anh, Trung, Nhật, Hàn, Pháp, Đức."
        )
    },
    {
        "id": "product_manager",
        "name": "🚀 Product Manager",
        "description": "Tư duy sản phẩm, user story và roadmap",
        "system_prompt": (
            "Bạn là một Product Manager giàu kinh nghiệm từ Big Tech. "
            "Hãy:\n"
            "- Tư duy từ góc độ user-centric\n"
            "- Viết user stories theo chuẩn INVEST\n"
            "- Prioritize features theo framework RICE/MoSCoW\n"
            "- Đặt câu hỏi về business metrics và success criteria\n"
            "- Cân bằng giữa technical feasibility và business value"
        )
    },
    {
        "id": "debater",
        "name": "⚡ Tranh luận",
        "description": "Luôn đưa ra quan điểm đối lập để thúc đẩy tư duy",
        "system_prompt": (
            "Bạn là một người tranh luận xuất sắc theo phong cách Devil's Advocate. "
            "Dù đồng ý hay không, bạn LUÔN tìm góc độ đối lập để:\n"
            "- Thử thách assumptions của người hỏi\n"
            "- Trình bày quan điểm ngược lại một cách thuyết phục\n"
            "- Nêu rõ trade-offs và consequences\n"
            "Mục tiêu là giúp người dùng suy nghĩ toàn diện hơn."
        )
    },
    {
        "id": "researcher",
        "name": "🔬 Nhà nghiên cứu",
        "description": "Nghiên cứu chuyên sâu, trích dẫn nguồn và tổng hợp thông tin",
        "system_prompt": (
            "Bạn là một nhà nghiên cứu học thuật nghiêm túc. "
            "Hãy:\n"
            "- Trình bày thông tin có căn cứ và trích dẫn nguồn\n"
            "- Phân biệt rõ fact vs opinion vs hypothesis\n"
            "- Nêu các nghiên cứu liên quan khi có\n"
            "- Thừa nhận uncertainty khi chưa chắc chắn\n"
            "- Tổng hợp nhiều nguồn để đưa ra kết luận balanced"
        )
    }
]


# ── Library Store ──────────────────────────────────────────────

class AgentLibrary:
    """Persistent store for saved agent configurations."""

    def __init__(self):
        self._agents: dict = self._load()

    def _load(self) -> dict:
        if LIBRARY_FILE.exists():
            try:
                with open(LIBRARY_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        with open(LIBRARY_FILE, "w") as f:
            json.dump(self._agents, f, indent=2, ensure_ascii=False)

    def list_agents(self) -> list[dict]:
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> Optional[dict]:
        return self._agents.get(agent_id)

    def save_agent(self, config: dict) -> dict:
        agent_id = config.get("id") or str(uuid.uuid4())[:8]
        config["id"] = agent_id
        config["updated_at"] = time.time()
        if "created_at" not in config:
            config["created_at"] = time.time()
        self._agents[agent_id] = config
        self._save()
        return config

    def delete_agent(self, agent_id: str) -> bool:
        if agent_id in self._agents:
            del self._agents[agent_id]
            self._save()
            return True
        return False

    def duplicate_agent(self, agent_id: str) -> Optional[dict]:
        original = self._agents.get(agent_id)
        if not original:
            return None
        new_config = dict(original)
        new_config["id"] = str(uuid.uuid4())[:8]
        new_config["name"] = original["name"] + " (copy)"
        new_config["created_at"] = time.time()
        new_config["updated_at"] = time.time()
        self._agents[new_config["id"]] = new_config
        self._save()
        return new_config


_library: Optional[AgentLibrary] = None

def get_library() -> AgentLibrary:
    global _library
    if _library is None:
        _library = AgentLibrary()
    return _library


# ── Health Check ───────────────────────────────────────────────

async def check_agent_health(provider: str, model: str, api_key: Optional[str] = None) -> dict:
    """
    Send a minimal test message to verify the agent works.
    Returns: { ok, latency_ms, error, token_info }
    """
    from auth import get_store
    store = get_store()
    resolved_key = api_key or store.get_api_key(provider)

    start = time.time()

    try:
        if provider == "gemini":
            result = await _health_gemini(resolved_key, model, store)
        elif provider == "openai":
            result = await _health_openai(resolved_key, model)
        elif provider == "anthropic":
            result = await _health_anthropic(resolved_key, model)
        elif provider == "openrouter":
            result = await _health_openrouter(resolved_key, model, store)
        elif provider == "freemodel":
            result = await _health_freemodel(resolved_key, model, store)
        elif provider == "litert_lm":
            result = await _health_litert_lm(resolved_key, model)
        else:
            result = {"ok": False, "error": f"Unknown provider: {provider}"}

        result["latency_ms"] = round((time.time() - start) * 1000)
        return result

    except asyncio.TimeoutError:
        return {"ok": False, "error": "Timeout (>10s)", "latency_ms": 10000}
    except Exception as e:
        return {"ok": False, "error": str(e), "latency_ms": round((time.time() - start) * 1000)}


async def _health_gemini(api_key: Optional[str], model: str, store) -> dict:
    if not api_key:
        # Try OAuth
        try:
            from auth import get_google_credentials
            from google import genai as gai
            creds = get_google_credentials()
            if not creds:
                return {"ok": False, "error": "No API key or OAuth token configured"}
            client = gai.Client(credentials=creds)
            resp = await asyncio.wait_for(
                asyncio.to_thread(
                    lambda: client.models.generate_content(model=model or "gemini-2.0-flash", contents="Hi")
                ), timeout=10.0
            )
            return {"ok": True, "token_info": _extract_gemini_usage(resp)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    try:
        from google.antigravity import Agent as AGYAgent, LocalAgentConfig
        config = LocalAgentConfig(api_key=api_key, model=model or "gemini-2.0-flash")
        async with AGYAgent(config=config) as agent:
            resp = await asyncio.wait_for(agent.chat("Hi, reply with just: OK"), timeout=10.0)
            full = ""
            async for tok in resp:
                full += tok
            return {"ok": True, "token_info": None, "sample": full[:50]}
    except Exception:
        pass

    try:
        from google import genai as gai
        client = gai.Client(api_key=api_key)
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.models.generate_content(model=model or "gemini-2.0-flash", contents="Hi")
            ), timeout=10.0
        )
        return {"ok": True, "token_info": _extract_gemini_usage(resp)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _extract_gemini_usage(resp) -> Optional[dict]:
    try:
        u = resp.usage_metadata
        return {
            "prompt_tokens": u.prompt_token_count,
            "completion_tokens": u.candidates_token_count,
            "total_tokens": u.total_token_count,
        }
    except Exception:
        return None


async def _health_openai(api_key: Optional[str], model: str) -> dict:
    if not api_key:
        return {"ok": False, "error": "No API key configured"}
    try:
        import openai as oai
        client = oai.AsyncOpenAI(api_key=api_key)
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model or "gpt-4o-mini",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            ), timeout=10.0
        )
        usage = resp.usage
        return {
            "ok": True,
            "token_info": {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
        }
    except oai.RateLimitError as e:
        return {"ok": False, "error": "Rate limit reached", "rate_limited": True, "detail": str(e)}
    except oai.AuthenticationError:
        return {"ok": False, "error": "Invalid API key"}
    except oai.BadRequestError as e:
        return {"ok": False, "error": f"Bad request: {e}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _health_anthropic(api_key: Optional[str], model: str) -> dict:
    if not api_key:
        return {"ok": False, "error": "No API key configured"}
    try:
        import anthropic as ant
        client = ant.AsyncAnthropic(api_key=api_key)
        resp = await asyncio.wait_for(
            client.messages.create(
                model=model or "claude-3-5-haiku-20241022",
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}],
            ), timeout=10.0
        )
        usage = resp.usage
        return {
            "ok": True,
            "token_info": {
                "prompt_tokens": usage.input_tokens,
                "completion_tokens": usage.output_tokens,
                "total_tokens": usage.input_tokens + usage.output_tokens,
            }
        }
    except ant.RateLimitError as e:
        return {"ok": False, "error": "Rate limit reached", "rate_limited": True, "detail": str(e)}
    except ant.AuthenticationError:
        return {"ok": False, "error": "Invalid API key"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _health_openrouter(api_key: Optional[str], model: str, store) -> dict:
    if not api_key:
        return {"ok": False, "error": "No API key configured"}
    try:
        import openai as oai
        base_url = store.get_base_url("openrouter") or "https://openrouter.ai/api/v1"
        client = oai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model or "google/gemini-2.5-flash",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
                extra_headers={"HTTP-Referer": "http://localhost:8000", "X-Title": "AI Agent Chat"},
            ), timeout=10.0
        )
        usage = resp.usage
        return {
            "ok": True,
            "token_info": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            } if usage else None
        }
    except Exception as e:
        err = str(e)
        if "rate" in err.lower():
            return {"ok": False, "error": "Rate limit reached", "rate_limited": True}
        if "auth" in err.lower() or "401" in err:
            return {"ok": False, "error": "Invalid API key"}
        return {"ok": False, "error": err}


async def _health_freemodel(api_key: Optional[str], model: str, store) -> dict:
    if not api_key:
        return {"ok": False, "error": "No API key configured"}
    try:
        import openai as oai
        base_url = store.get_base_url("freemodel") or "https://api.freemodel.dev/v1"
        client = oai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        resp = await asyncio.wait_for(
            client.chat.completions.create(
                model=model or "fre-5.5",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=5,
            ), timeout=10.0
        )
        usage = resp.usage
        return {
            "ok": True,
            "token_info": {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": usage.total_tokens if usage else 0,
            } if usage else None
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _health_litert_lm(api_key: Optional[str], model: str) -> dict:
    if not model or not model.strip():
        return {"ok": False, "error": "Model path is empty"}
    import os
    model_path = os.path.abspath(os.path.expanduser(model.strip()))
    if not os.path.exists(model_path):
        return {"ok": False, "error": f"Model file not found at path: {model_path}"}
    try:
        import litert_lm
    except ImportError:
        return {"ok": False, "error": "Package `litert-lm-api` is not installed"}

    try:
        def load_and_test():
            try:
                try:
                    engine = litert_lm.Engine(model_path, backend=litert_lm.Backend.GPU())
                except Exception:
                    engine = litert_lm.Engine(model_path, backend=litert_lm.Backend.CPU())
                
                with engine.create_conversation() as conn:
                    resp = conn.send_message("Say: OK")
                    text = resp["content"][0]["text"]
                    return {"ok": True, "sample": text[:50], "token_info": None}
            except Exception as ex:
                return {"ok": False, "error": str(ex)}

        return await asyncio.wait_for(asyncio.to_thread(load_and_test), timeout=15.0)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Health check timed out (>15s)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
