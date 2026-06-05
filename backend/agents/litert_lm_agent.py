import asyncio
import os
from typing import AsyncGenerator, Optional
from .base_agent import BaseAgent

try:
    import litert_lm
    HAS_LITERT = True
except ImportError:
    HAS_LITERT = False

# Global cache for LiteRT-LM engines to avoid reloading model weights repeatedly
_engines_cache = {}
_engines_lock = asyncio.Lock()


class LiteRTLMAgent(BaseAgent):
    """AI Agent powered by LiteRT-LM (local on-device models)."""

    def __init__(
        self,
        name: str = "LiteRT",
        model: str = "",  # Absolute path to the .litertlm file
        system_prompt: str = "",
        avatar_emoji: str = "⚙️",
        api_key: Optional[str] = None,
    ):
        super().__init__(
            name=name,
            provider="litert_lm",
            model=model,
            system_prompt=system_prompt,
            avatar_emoji=avatar_emoji,
            api_key=api_key,
        )

    async def chat_stream(
        self,
        messages: list[dict],
        context_response: Optional[str] = None,
        context_agent: Optional[str] = None,
        room_agents: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream responses from local LiteRT-LM model."""
        if not HAS_LITERT:
            yield (
                "⚠️ **Lỗi cấu hình**: Package `ai-edge-litert` chưa được cài.\n"
                "Hãy chạy: `pip install ai-edge-litert`"
            )
            return

        if not self.model or not self.model.strip():
            yield (
                "⚠️ **LiteRT-LM Model Path trống**.\n\n"
                "Vui lòng chỉnh sửa cấu hình Agent này và điền đường dẫn tuyệt đối đến file `.litertlm` của bạn."
            )
            return

        # Expand user directory (~/...) if needed
        model_path = os.path.abspath(os.path.expanduser(self.model.strip()))

        if not os.path.exists(model_path):
            yield (
                f"⚠️ **Không tìm thấy file model**: `{model_path}`\n\n"
                "Vui lòng kiểm tra lại đường dẫn file model trên máy của bạn."
            )
            return

        system_prompt = self.build_system_prompt_with_context(
            context_response, context_agent, room_agents
        )

        # Build litert_lm Messages list
        litert_messages = [litert_lm.Message.system(system_prompt)]
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            agent_name = msg.get("agent_name", "")
            if role == "user":
                litert_messages.append(litert_lm.Message.user(content))
            else:
                display = f"[{agent_name}]: {content}" if agent_name else content
                litert_messages.append(litert_lm.Message.model(display))

        # Retrieve or initialize the Engine
        async with _engines_lock:
            if model_path not in _engines_cache:
                try:
                    # Attempt GPU backend first for acceleration (Metal/NPU/CUDA)
                    engine = litert_lm.Engine(model_path, backend=litert_lm.Backend.GPU())
                    _engines_cache[model_path] = engine
                except Exception as gpu_err:
                    print(f"[WARN] Failed to load LiteRT-LM model on GPU: {gpu_err}. Falling back to CPU...")
                    try:
                        # Fall back to standard CPU backend
                        engine = litert_lm.Engine(model_path, backend=litert_lm.Backend.CPU())
                        _engines_cache[model_path] = engine
                    except Exception as cpu_err:
                        yield f"⚠️ **Lỗi nạp model LiteRT-LM**: {cpu_err} (GPU error: {gpu_err})"
                        return

            engine = _engines_cache[model_path]

        # LiteRT-LM runs synchronous inference. Wrap it in a thread executor with a queue.
        try:
            # Last message is the user prompt
            last_message = litert_messages[-1]
            user_input = last_message.content if hasattr(last_message, "content") else str(last_message)
            if hasattr(last_message, "content") and isinstance(last_message.content, list):
                user_input = last_message.content[0].get("text", "") if last_message.content else ""

            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def run_generation():
                try:
                    # Initialize conversation with history (all messages except the last user query)
                    with engine.create_conversation(messages=litert_messages[:-1]) as conversation:
                        for chunk in conversation.send_message_async(user_input):
                            try:
                                text = chunk["content"][0]["text"]
                                if text:
                                    loop.call_soon_threadsafe(queue.put_nowait, text)
                            except Exception:
                                pass
                except Exception as e:
                    loop.call_soon_threadsafe(queue.put_nowait, e)
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            # Start background thread execution
            loop.run_in_executor(None, run_generation)

            while True:
                token = await queue.get()
                if token is None:
                    break
                if isinstance(token, Exception):
                    yield f"\n⚠️ **Lỗi trong quá trình suy luận**: {token}"
                    break
                yield token

        except Exception as e:
            yield f"⚠️ **Lỗi khởi chạy conversation**: {e}"
