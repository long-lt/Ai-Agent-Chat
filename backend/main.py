import json
import uuid
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from pydantic import BaseModel

import database
import config
from chat_room import ChatRoom, create_agent
import agent_library as lib_module
from agent_library import get_library, BUILTIN_SKILLS, check_agent_health


# In-memory room store
_rooms: dict[str, ChatRoom] = {}

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    await database.init_db()
    # Load existing rooms from DB
    rooms = await database.list_rooms()
    for room_data in rooms:
        try:
            agents = [create_agent(a) for a in room_data["agents_config"]]
            room = ChatRoom(room_data["id"], room_data["name"], agents)
            await room.load_history()
            _rooms[room_data["id"]] = room
        except Exception as e:
            print(f"[WARN] Could not restore room {room_data['id']}: {e}")
    print(f"[INFO] Loaded {len(_rooms)} rooms from database.")
    yield


app = FastAPI(title="AI Agent Group Chat", lifespan=lifespan)


# ── Static files ──────────────────────────────────────────────────────────────

@app.get("/")
async def serve_index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Frontend not found"}


@app.get("/styles.css")
async def serve_css():
    return FileResponse(FRONTEND_DIR / "styles.css")


@app.get("/app.js")
async def serve_js():
    return FileResponse(FRONTEND_DIR / "app.js")


# ── REST API ──────────────────────────────────────────────────────────────────

class CreateRoomRequest(BaseModel):
    name: str
    agents: list[dict]  # list of agent config dicts


@app.post("/api/rooms")
async def create_room(req: CreateRoomRequest):
    """Create a new chat room with specified agents."""
    room_id = str(uuid.uuid4())[:8]
    try:
        agents = [create_agent(a) for a in req.agents]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    room = ChatRoom(room_id, req.name, agents)
    _rooms[room_id] = room

    # Persist to DB (store config without sensitive api_key)
    agents_config = [
        {k: v for k, v in a.items() if k != "api_key"}
        for a in req.agents
    ]
    await database.save_room(room_id, req.name, agents_config)

    return {
        "room_id": room_id,
        "name": req.name,
        "agents": [a.to_dict() for a in agents],
    }


@app.get("/api/rooms")
async def list_rooms():
    """List all rooms."""
    result = []
    for room_id, room in _rooms.items():
        result.append({
            "room_id": room_id,
            "name": room.name,
            "agents": room.get_agents_info(),
        })
    return result


@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str):
    """Get room info."""
    room = _rooms.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return {
        "room_id": room_id,
        "name": room.name,
        "agents": room.get_agents_info(),
    }


@app.get("/api/rooms/{room_id}/history")
async def get_history(room_id: str, limit: int = 100):
    """Get chat history for a room."""
    room = _rooms.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    messages = await database.get_messages(room_id, limit)
    return messages


@app.delete("/api/rooms/{room_id}")
async def delete_room(room_id: str):
    """Delete a room."""
    if room_id not in _rooms:
        raise HTTPException(status_code=404, detail="Room not found")
    del _rooms[room_id]
    await database.delete_room(room_id)
    return {"ok": True}


@app.put("/api/rooms/{room_id}")
async def update_room(room_id: str, req: CreateRoomRequest):
    """Update an existing chat room's name and agents list."""
    room = _rooms.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    try:
        agents = [create_agent(a) for a in req.agents]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update in-memory room
    room.name = req.name
    room.agents = agents

    # Persist to DB
    agents_config = [
        {k: v for k, v in a.items() if k != "api_key"}
        for a in req.agents
    ]
    await database.save_room(room_id, req.name, agents_config)

    # Broadcast new room info to all clients in the room
    await room.broadcast({
        "type": "room_info",
        "room_id": room_id,
        "name": room.name,
        "agents": room.get_agents_info(),
    })

    return {
        "room_id": room_id,
        "name": room.name,
        "agents": [a.to_dict() for a in agents],
    }



@app.get("/api/config/defaults")
async def get_defaults():
    """Return default agent configs (without api keys)."""
    return {
        "default_agents": [
            {k: v for k, v in a.items() if k != "api_key"}
            for a in config.DEFAULT_AGENTS
        ]
    }


from models_helper import get_provider_models

@app.get("/api/models/{provider}")
async def list_provider_models(provider: str, api_key: str = None):
    """
    List available models for a provider.
    Tries to fetch from the official API if credentials exist,
    otherwise falls back to a curated list of popular models.
    """
    try:
        return await get_provider_models(provider, api_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))









@app.websocket("/ws/{room_id}")
async def websocket_chat(websocket: WebSocket, room_id: str):
    """WebSocket endpoint for real-time chat."""
    await websocket.accept()

    room = _rooms.get(room_id)
    if not room:
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": f"Room '{room_id}' not found."
        }))
        await websocket.close()
        return

    room.add_connection(websocket)

    # Send room info on connect
    await websocket.send_text(json.dumps({
        "type": "room_info",
        "room_id": room_id,
        "name": room.name,
        "agents": room.get_agents_info(),
    }))

    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                payload = {"type": "message", "content": data}

            msg_type = payload.get("type", "message")

            if msg_type == "message":
                content = payload.get("content", "").strip()
                if content:
                    await room.handle_message(content)

            elif msg_type == "retry_agent":
                agent_name = payload.get("agent_name", "")
                if agent_name:
                    asyncio.create_task(room.retry_agent(agent_name))

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    finally:
        room.remove_connection(websocket)


# ── Agent Library API ────────────────────────────────────────────────────────

class SaveAgentLibRequest(BaseModel):
    id: str = ""
    name: str
    provider: str
    model: str
    avatar_emoji: str = "🤖"
    system_prompt: str = ""
    api_key: str = ""
    description: str = ""


@app.get("/api/library/agents")
async def list_library_agents():
    """List all saved agents in the library."""
    return {"agents": get_library().list_agents()}


@app.post("/api/library/agents")
async def save_library_agent(req: SaveAgentLibRequest):
    """Create or update an agent in the library."""
    config_dict = req.model_dump()
    agent = get_library().save_agent(config_dict)
    return agent


@app.delete("/api/library/agents/{agent_id}")
async def delete_library_agent(agent_id: str):
    """Delete an agent from the library."""
    ok = get_library().delete_agent(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"ok": True}


@app.post("/api/library/agents/{agent_id}/duplicate")
async def duplicate_library_agent(agent_id: str):
    """Duplicate an agent in the library."""
    agent = get_library().duplicate_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.get("/api/library/skills")
async def list_skills():
    """List built-in skills/system prompt presets."""
    return {"skills": BUILTIN_SKILLS}


@app.post("/api/library/agents/{agent_id}/health")
async def agent_health_check(agent_id: str):
    """Run a health check on a library agent."""
    agent = get_library().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await check_agent_health(
        provider=agent["provider"],
        model=agent["model"],
        api_key=agent.get("api_key") or None,
    )
    return result


@app.post("/api/health-check")
async def quick_health_check(req: dict):
    """Quick health check for any provider/model/key combo."""
    provider = req.get("provider", "")
    model = req.get("model", "")
    api_key = req.get("api_key") or None
    if not provider:
        raise HTTPException(status_code=400, detail="provider required")
    result = await check_agent_health(provider=provider, model=model, api_key=api_key)
    return result


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=config.HOST, port=config.PORT, reload=True)


@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    # Simple lightning bolt SVG favicon
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><text y="20" font-size="20">⚡</text></svg>'.encode('utf-8')
    return Response(content=svg, media_type="image/svg+xml")
