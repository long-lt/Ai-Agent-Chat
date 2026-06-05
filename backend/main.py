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
import auth as auth_module
from auth import get_store
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
        {**a, "api_key": a.get("api_key", "")}
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
        {**a, "api_key": a.get("api_key", "")}
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




# ── Settings & Credentials API ────────────────────────────────────────────────

@app.get("/api/settings/status")
async def settings_status():
    """Return auth/credential status for all providers."""
    return get_store().get_status()


class SaveKeyRequest(BaseModel):
    provider: str
    api_key: str


@app.post("/api/settings/api-key")
async def save_api_key(req: SaveKeyRequest):
    """Save an API key for a provider to credentials.json."""
    if req.provider not in ("gemini", "openai", "anthropic", "openrouter", "freemodel"):
        raise HTTPException(status_code=400, detail="Unknown provider")
    if not req.api_key.strip():
        get_store().delete_api_key(req.provider)
        return {"ok": True, "message": f"{req.provider} API key removed"}
    get_store().set_api_key(req.provider, req.api_key.strip())
    return {"ok": True, "message": f"{req.provider} API key saved"}


class SaveBaseUrlRequest(BaseModel):
    provider: str
    base_url: str


@app.post("/api/settings/base-url")
async def save_base_url(req: SaveBaseUrlRequest):
    """Save a base URL for a provider to credentials.json."""
    if req.provider not in ("gemini", "openai", "anthropic", "openrouter", "freemodel"):
        raise HTTPException(status_code=400, detail="Unknown provider")
    if not req.base_url.strip():
        get_store().set_base_url(req.provider, "")
        return {"ok": True, "message": f"{req.provider} Base URL cleared"}
    get_store().set_base_url(req.provider, req.base_url.strip())
    return {"ok": True, "message": f"{req.provider} Base URL saved"}


@app.delete("/api/settings/api-key/{provider}")
async def delete_api_key(provider: str):
    """Remove a saved API key."""
    get_store().delete_api_key(provider)
    return {"ok": True}


class SaveGoogleClientRequest(BaseModel):
    client_id: str
    client_secret: str


@app.post("/api/settings/google-client")
async def save_google_client(req: SaveGoogleClientRequest):
    """Save Google OAuth2 client credentials."""
    if not req.client_id.strip() or not req.client_secret.strip():
        raise HTTPException(status_code=400, detail="client_id and client_secret are required")
    get_store().save_google_client_config(req.client_id.strip(), req.client_secret.strip())
    return {"ok": True, "message": "Google OAuth client saved"}


@app.post("/api/settings/upload-file")
async def upload_credential_file(file: UploadFile):
    """Upload a credential file (client_secret.json or oauth_creds.json)."""
    filename = file.filename
    if filename not in ("client_secret.json", "oauth_creds.json", "credentials.json"):
        raise HTTPException(
            status_code=400,
            detail="Chỉ chấp nhận các file: client_secret.json, oauth_creds.json, credentials.json"
        )

    # Read and parse JSON content to ensure it is valid
    try:
        content = await file.read()
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="File không phải định dạng JSON hợp lệ.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi đọc file: {str(e)}")

    dest_path = auth_module.BACKEND_DIR / filename
    try:
        with open(dest_path, "w") as f:
            json.dump(data, f, indent=2)

        # Clear active store caching if config files changed
        if filename == "credentials.json":
            auth_module._store = None

        return {"ok": True, "message": f"Đã lưu file {filename} thành công!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi lưu file: {str(e)}")


@app.delete("/api/settings/file/{filename}")
async def delete_credential_file(filename: str):
    """Delete an uploaded credential file."""
    if filename not in ("client_secret.json", "oauth_creds.json", "credentials.json"):
        raise HTTPException(status_code=400, detail="Tên file không hợp lệ")

    dest_path = auth_module.BACKEND_DIR / filename
    if dest_path.exists():
        try:
            dest_path.unlink()
            if filename == "credentials.json":
                auth_module._store = None
            return {"ok": True, "message": f"Đã xóa file {filename}"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi khi xóa file: {str(e)}")
    else:
        raise HTTPException(status_code=404, detail="File không tồn tại")



# ── Google OAuth2 Flow ────────────────────────────────────────────────────────

@app.get("/api/auth/google/login")
async def google_oauth_login(request: Request):
    """Initiate Google OAuth2 login flow."""
    redirect_uri = str(request.base_url).rstrip("/") + "/api/auth/google/callback"
    try:
        auth_url, state = auth_module.start_google_oauth(redirect_uri)
        return RedirectResponse(url=auth_url)
    except ValueError as e:
        # Return a helpful HTML page instead of bare error
        html = f"""
        <!DOCTYPE html><html><head>
        <title>OAuth Setup Required</title>
        <style>
          body {{ font-family: system-ui; background: #0e1221; color: #e8eaf2;
                 display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
          .box {{ background: #1c2236; border: 1px solid rgba(255,255,255,0.1);
                  border-radius: 16px; padding: 32px; max-width: 520px; }}
          h2 {{ color: #f87171; margin-bottom: 16px; }}
          pre {{ background: #0d1117; padding: 14px; border-radius: 8px; font-size: 13px;
                 overflow-x: auto; white-space: pre-wrap; }}
          a {{ color: #7c7fff; }}
          .btn {{ display: inline-block; margin-top: 20px; padding: 10px 20px;
                  background: #6c6fff; color: white; text-decoration: none;
                  border-radius: 8px; font-weight: 600; }}
        </style></head><body>
        <div class="box">
          <h2>⚙️ OAuth Client Chưa Được Cấu Hình</h2>
          <p>{str(e)}</p>
          <p>Để dùng Google OAuth, bạn cần:</p>
          <ol>
            <li>Tạo OAuth2 Client tại <a href="https://console.cloud.google.com/apis/credentials" target="_blank">Google Cloud Console</a></li>
            <li>Chọn <strong>Web application</strong>, thêm redirect URI:<br>
              <pre>{redirect_uri}</pre></li>
            <li>Tải <strong>client_secret.json</strong> và đặt vào thư mục <code>backend/</code>,<br>
              <em>hoặc</em> nhập Client ID + Secret trong <strong>Settings → Gemini</strong></li>
          </ol>
          <a class="btn" href="/">← Quay lại</a>
        </div></body></html>
        """
        return HTMLResponse(content=html, status_code=400)


@app.get("/api/auth/google/callback")
async def google_oauth_callback(request: Request, code: str = None, state: str = None, error: str = None):
    """Handle Google OAuth2 callback."""
    if error:
        return HTMLResponse(
            content=f"<script>window.opener?.postMessage({{type:'oauth_error',error:'{error}'}},'*');window.close();</script>",
            status_code=200,
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")

    try:
        token_data = auth_module.complete_google_oauth(code, state)

        # Try to get user info for display
        creds = auth_module.get_google_credentials()
        user_info = auth_module.get_google_user_info(creds) if creds else {}
        email = user_info.get("email", "")
        name = user_info.get("name", "Google User")

        # Success page — posts message to opener and closes
        html = f"""
        <!DOCTYPE html><html><head>
        <title>Login Thành Công</title>
        <style>
          body {{ font-family: system-ui; background: #0e1221; color: #e8eaf2;
                 display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
          .box {{ background: #1c2236; border: 1px solid rgba(255,255,255,0.1);
                  border-radius: 16px; padding: 40px; text-align:center; max-width: 360px; }}
          .icon {{ font-size: 48px; margin-bottom: 16px; }}
          h2 {{ color: #4ade80; margin-bottom: 8px; }}
          p {{ color: #8892b0; font-size: 14px; }}
        </style>
        <script>
          // Notify the parent window
          if (window.opener) {{
            window.opener.postMessage({{
              type: 'oauth_success',
              provider: 'gemini',
              email: '{email}',
              name: '{name}'
            }}, '*');
          }}
          setTimeout(() => window.close(), 2000);
        </script>
        </head><body>
        <div class="box">
          <div class="icon">✅</div>
          <h2>Đăng nhập thành công!</h2>
          <p>Xin chào, <strong>{name}</strong>!<br>{email}</p>
          <p style="margin-top:12px; font-size:12px;">Cửa sổ này sẽ tự đóng...</p>
        </div></body></html>
        """
        return HTMLResponse(content=html)
    except Exception as e:
        return HTMLResponse(
            content=f"""
            <script>
              if (window.opener) window.opener.postMessage({{type:'oauth_error',error:'{str(e)}'}}, '*');
              setTimeout(() => window.close(), 3000);
            </script>
            <p style="color:red">Lỗi: {str(e)}</p>
            """,
            status_code=200,
        )


@app.get("/api/auth/google/status")
async def google_auth_status():
    """Get Google OAuth status and user info."""
    creds = auth_module.get_google_credentials()
    if not creds:
        return {"authenticated": False}
    user_info = auth_module.get_google_user_info(creds) or {}
    return {
        "authenticated": True,
        "email": user_info.get("email"),
        "name": user_info.get("name"),
        "picture": user_info.get("picture"),
    }


@app.delete("/api/auth/google/logout")
async def google_logout():
    """Remove stored Google OAuth tokens."""
    get_store().delete_oauth_token()
    return {"ok": True, "message": "Logged out from Google"}




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
