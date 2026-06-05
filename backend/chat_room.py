import asyncio
import json
import re
import time
from typing import Callable, Optional

from agents.base_agent import BaseAgent
from agents.gemini_agent import GeminiAgent
from agents.openai_agent import OpenAIAgent
from agents.anthropic_agent import AnthropicAgent
from agents.openrouter_agent import OpenRouterAgent
from agents.freemodel_agent import FreemodelAgent
from agents.litert_lm_agent import LiteRTLMAgent
import database
import config
from models_helper import get_provider_models


def create_agent(agent_config: dict) -> BaseAgent:
    """Factory function to create an agent from a config dict."""
    provider = agent_config.get("provider", "gemini")
    kwargs = {
        "name": agent_config.get("name", "Agent"),
        "model": agent_config.get("model", ""),
        "system_prompt": agent_config.get("system_prompt", ""),
        "avatar_emoji": agent_config.get("avatar_emoji", "🤖"),
        "api_key": agent_config.get("api_key") or None,
    }

    if provider == "gemini":
        return GeminiAgent(**kwargs)
    elif provider == "openai":
        return OpenAIAgent(**kwargs)
    elif provider == "anthropic":
        return AnthropicAgent(**kwargs)
    elif provider == "openrouter":
        return OpenRouterAgent(**kwargs)
    elif provider == "freemodel" or provider == "mimo":
        return FreemodelAgent(**kwargs)
    elif provider == "litert_lm":
        return LiteRTLMAgent(**kwargs)
    else:
        raise ValueError(f"Unknown provider: {provider}")


class ChatRoom:
    """Manages a chat room with multiple AI agents."""

    def __init__(self, room_id: str, name: str, agents: list[BaseAgent]):
        self.room_id = room_id
        self.name = name
        self.agents = agents
        self._history: list[dict] = []
        self._active_connections: set = set()
        self._broadcast_lock = asyncio.Lock()

    def add_connection(self, ws):
        self._active_connections.add(ws)

    def remove_connection(self, ws):
        self._active_connections.discard(ws)

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected WebSocket clients sequentially."""
        data = json.dumps(message, ensure_ascii=False)
        async with self._broadcast_lock:
            dead = set()
            for ws in self._active_connections:
                try:
                    await ws.send_text(data)
                except Exception:
                    dead.add(ws)
            for ws in dead:
                self._active_connections.discard(ws)

    def get_mentioned_agents(self, text: str) -> list[BaseAgent]:
        """Extract @mentioned agents from text."""
        mentioned_names = re.findall(r"@(\w+)", text)
        mentioned = []
        for name in mentioned_names:
            for agent in self.agents:
                if agent.name.lower() == name.lower():
                    mentioned.append(agent)
                    break
        return mentioned

    async def handle_message(self, user_message: str):
        """Process a user message: save it, then dispatch to agents."""
        # Save user message to history and DB
        msg_entry = {
            "role": "user",
            "content": user_message,
            "timestamp": time.time(),
        }
        self._history.append(msg_entry)
        await database.save_message(self.room_id, "user", user_message)

        # Snapshot of history before the current user message (without msg_entry)
        history_before_user = [
            m for m in self._history[:-1]
        ]

        # Broadcast user message back to other clients (and update sender)
        await self.broadcast({
            "type": "user_message",
            "content": user_message,
            "timestamp": msg_entry["timestamp"],
        })

        # Determine which agents respond
        mentioned = self.get_mentioned_agents(user_message)
        if mentioned:
            responding_agents = mentioned
        else:
            responding_agents = list(self.agents)

        if not responding_agents:
            return

        # Sequentially stream responses from all responding agents
        responses_so_far = {}
        for agent in responding_agents:
            context_text = None
            if responses_so_far:
                context_text = self._build_combined_context(responses_so_far)
                
            response = await self._stream_agent_response(
                agent=agent,
                messages=history_before_user,
                user_message=user_message,
                context_response=context_text,
                context_agent="Các agent trước đó" if responses_so_far else None,
                room_agents=[a.name for a in self.agents]
            )
            
            if response and response != "[SKIP]":
                self._add_agent_message(agent, response)
                responses_so_far[agent.name] = response

        # Trigger debate phase if there are multiple agents
        # (Though with sequential processing, the debate phase is mostly handled in the first pass.
        # But we keep it in case someone wants to explicitly rebut the last agent's comment)
        if responses_so_far and len(self.agents) > 1:
            await self._agent_debate_phase(
                responses_so_far=responses_so_far,
                user_message=user_message,
                round_num=1,
            )

    def _build_combined_context(self, responses: dict[str, str]) -> str:
        """Combine multiple agent responses into context string."""
        parts = []
        for agent_name, response in responses.items():
            parts.append(f"**{agent_name}**: {response}")
        return "\n\n".join(parts)

    async def _silent_agent_response(
        self,
        agent: BaseAgent,
        messages: list[dict],
        user_message: str,
    ) -> str:
        """Get a response from an agent without broadcasting to UI."""
        agent_messages = list(messages)
        agent_messages.append({"role": "user", "content": user_message})
        
        full_response = ""
        try:
            async for token in agent.chat_stream(
                messages=agent_messages,
                context_response=None,
                context_agent=None,
                room_agents=None,
            ):
                if token != "[SKIP]":
                    full_response += token
        except Exception:
            pass
        return full_response

    async def _check_consensus(self, responses_so_far: dict[str, str]) -> int:
        """Use the first agent as a Judge to evaluate consensus (0-10)."""
        if not self.agents:
            return 0
        judge = self.agents[0]
        context_text = self._build_combined_context(responses_so_far)
        
        prompt = (
            "Bạn là một Trọng tài. Hãy đọc các ý kiến dưới đây của các AI Agent và đánh giá "
            "mức độ đồng thuận của họ trên thang điểm từ 0 đến 10 (0 = hoàn toàn mâu thuẫn, "
            "10 = hoàn toàn đồng ý và thống nhất).\n\n"
            f"Ý kiến:\n{context_text}\n\n"
            "Chỉ trả lời bằng MỘT CON SỐ DUY NHẤT (ví dụ: 8). Không giải thích thêm."
        )
        
        score_str = await self._silent_agent_response(judge, self._history, prompt)
        score_str = score_str.strip()
        import re
        match = re.search(r'\d+', score_str)
        if match:
            try:
                return int(match.group(0))
            except ValueError:
                return 0
        return 0

    async def _generate_final_report(self, responses_so_far: dict[str, str], user_message: str):
        """Generate a final consensus report."""
        if not self.agents:
            return
        leader = self.agents[0]
        context_text = self._build_combined_context(responses_so_far)
        
        prompt = (
            "Nhóm của bạn đã đạt được đồng thuận. Hãy viết một BÁO CÁO TỔNG HỢP cuối cùng "
            "đúc kết lại các ý chính đã được thống nhất để trả lời cho câu hỏi gốc của người dùng.\n\n"
            f"Câu hỏi gốc: {user_message}\n\n"
            f"Các ý kiến đã thống nhất:\n{context_text}\n\n"
            "Trình bày rõ ràng, súc tích, bắt đầu bằng tiêu đề '📋 Báo cáo tổng hợp:'."
        )
        
        response = await self._stream_agent_response(
            agent=leader,
            messages=self._history,
            user_message=prompt,
            context_response=None,
            context_agent=None,
            is_debate=True,
            room_agents=[a.name for a in self.agents]
        )
        if response and response != "[SKIP]":
            self._add_agent_message(leader, response)

    async def _agent_debate_phase(
        self,
        responses_so_far: dict[str, str],
        user_message: str,
        round_num: int,
    ):
        """Allow agents to rebut each other until consensus (>= 8/10) or max rounds."""
        if round_num > config.MAX_AGENT_DEBATE_ROUNDS:
            return

        if len(self.agents) < 2:
            return

        # Check consensus
        score = await self._check_consensus(responses_so_far)
        if score >= 8:
            # Reached consensus!
            await self._generate_final_report(responses_so_far, user_message)
            return

        # Not enough consensus, trigger another round
        new_responses = {}
        for agent in self.agents:
            # Let agents read everyone else's response
            others_context = {
                k: v for k, v in responses_so_far.items() if k != agent.name
            }
            if not others_context:
                continue

            context_text = self._build_combined_context(others_context)

            rebuttal_prompt = (
                f"Chúng ta chưa đạt được đồng thuận (Điểm đồng thuận hiện tại: {score}/10). "
                f"Dưới đây là ý kiến của các agent khác:\n{context_text}\n\n"
                f"Hãy cố gắng tìm tiếng nói chung. "
                f"Nếu bạn đồng ý với họ, hãy nói ngắn gọn. Nếu bạn phản đối, hãy giải thích lý do để thuyết phục họ. "
                f"Nếu bạn không có gì để thêm, hãy trả lời chính xác: [SKIP]"
            )

            response = await self._stream_agent_response(
                agent=agent,
                messages=self._history,
                user_message=rebuttal_prompt,
                context_response=None,
                context_agent=None,
                is_debate=True,
                room_agents=[a.name for a in self.agents]
            )

            if response and response.strip() != "[SKIP]":
                self._add_agent_message(agent, response)
                new_responses[agent.name] = response

        if new_responses:
            # Merge old and new responses (newer overwrites older)
            merged_responses = dict(responses_so_far)
            merged_responses.update(new_responses)
            
            # Recurse for another debate round
            await self._agent_debate_phase(
                responses_so_far=merged_responses,
                user_message=user_message,
                round_num=round_num + 1,
            )

    async def _save_room_config(self):
        """Save current agents config to DB."""
        await database.save_room(
            self.room_id, 
            self.name, 
            [a.to_dict() for a in self.agents]
        )

    async def remove_agent(self, agent_name: str, reason: str = ""):
        """Remove an agent from the room and DB."""
        self.agents = [a for a in self.agents if a.name != agent_name]
        await self._save_room_config()
        await self.broadcast({
            "type": "agent_removed",
            "agent_name": agent_name,
            "reason": reason
        })

    async def _stream_agent_response(
        self,
        agent: BaseAgent,
        messages: list[dict],
        user_message: str,
        context_response: Optional[str],
        context_agent: Optional[str],
        is_debate: bool = False,
        room_agents: Optional[list[str]] = None,
    ) -> str:
        """Stream an agent's response via WebSocket, return full response.
        Includes automatic model fallback and timeout handling."""

        # Get fallback models
        try:
            available_models = await get_provider_models(agent.provider)
        except Exception:
            available_models = []

        models_to_try = [agent.model]
        for m in available_models:
            if m != agent.model:
                models_to_try.append(m)

        for attempt, model in enumerate(models_to_try):
            agent.model = model

            await self.broadcast({
                "type": "agent_typing",
                "agent": agent.to_dict(),
                "is_debate": is_debate,
            })

            agent_messages = list(messages)
            agent_messages.append({"role": "user", "content": user_message})

            full_response = ""
            try:
                stream = agent.chat_stream(
                    messages=agent_messages,
                    context_response=context_response,
                    context_agent=context_agent,
                    room_agents=room_agents,
                )
                
                if not hasattr(stream, '__anext__'):
                    stream = stream.__aiter__()

                while True:
                    try:
                        token = await asyncio.wait_for(stream.__anext__(), timeout=15.0)
                    except StopAsyncIteration:
                        break
                        
                    if token == "[SKIP]":
                        full_response = "[SKIP]"
                        break
                    full_response += token
                    await self.broadcast({
                        "type": "agent_token",
                        "agent": agent.to_dict(),
                        "token": token,
                        "is_debate": is_debate,
                    })

                # Success
                await self.broadcast({
                    "type": "agent_done",
                    "agent": agent.to_dict(),
                    "full_response": full_response,
                    "is_debate": is_debate,
                })
                
                if attempt > 0:
                    asyncio.create_task(self._save_room_config())
                
                return full_response

            except Exception as e:
                import traceback
                traceback.print_exc()
                
                if attempt < len(models_to_try) - 1:
                    await self.broadcast({
                        "type": "agent_retrying",
                        "agent": agent.to_dict(),
                        "error": f"Lỗi model {model}: {e}. Đang thử fallback xuống model khác...",
                        "attempt": attempt + 1,
                        "max_retries": len(models_to_try) - 1,
                        "wait_seconds": 2,
                    })
                    await self.broadcast({
                        "type": "agent_done",
                        "agent": agent.to_dict(),
                        "full_response": "",
                        "is_debate": is_debate,
                    })
                    await asyncio.sleep(2)
                    continue
                else:
                    await self.broadcast({
                        "type": "agent_error",
                        "agent": agent.to_dict(),
                        "error": str(e),
                        "retryable": False,
                    })
                    reason = "Toàn bộ model đều bị lỗi hoặc không phản hồi."
                    await self.remove_agent(agent.name, reason)
                    return ""

        return ""

    async def retry_agent(self, agent_name: str):
        """Retry a specific agent on the last user message."""
        # Find the agent
        agent = None
        for a in self.agents:
            if a.name == agent_name:
                agent = a
                break
        if not agent:
            return

        # Find the last user message from history
        last_user_msg = None
        history_before = []
        for i in range(len(self._history) - 1, -1, -1):
            if self._history[i]["role"] == "user":
                last_user_msg = self._history[i]["content"]
                history_before = self._history[:i]
                break

        if not last_user_msg:
            return

        response = await self._stream_agent_response(
            agent=agent,
            messages=history_before,
            user_message=last_user_msg,
            context_response=None,
            context_agent=None,
            room_agents=[a.name for a in self.agents]
        )
        if response and response != "[SKIP]":
            self._add_agent_message(agent, response)

    def _add_agent_message(self, agent: BaseAgent, content: str):
        """Add agent message to in-memory history and schedule DB save."""
        self._history.append({
            "role": "agent",
            "agent_name": agent.name,
            "provider": agent.provider,
            "content": content,
            "timestamp": time.time(),
        })
        # Schedule async DB save
        asyncio.create_task(
            database.save_message(
                self.room_id, "agent", content, agent.name, agent.provider
            )
        )

    async def load_history(self):
        """Load message history from database."""
        messages = await database.get_messages(self.room_id)
        self._history = [
            {
                "role": m["role"],
                "agent_name": m.get("agent_name"),
                "provider": m.get("provider"),
                "content": m["content"],
                "timestamp": m["timestamp"],
            }
            for m in messages
        ]
        return messages

    def get_agents_info(self) -> list[dict]:
        return [a.to_dict() for a in self.agents]

