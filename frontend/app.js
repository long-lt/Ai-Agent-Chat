/* ════════════════════════════════════════════════════════════
   AI Agent Group Chat — app.js
   WebSocket client · Multi-agent streaming · Room management
   ════════════════════════════════════════════════════════════ */

const API_BASE = window.location.origin;
const WS_BASE = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`;

// ── State ─────────────────────────────────────────────────────
const state = {
  rooms: [],           // [{room_id, name, agents}]
  currentRoomId: null,
  ws: null,
  activeStreams: {},   // { agentName: { el, textEl } }
  typingIndicators: {},// { agentName: el }
  agents: [],          // agents in current room
  pendingAgentConfig: null, // agent being configured in modal
  editingAgentIndex: null,  // for editing existing agents in room modal
  isEditingRoom: false,     // whether we are editing an existing room
  tempAgents: [],      // agents in room modal editor
  defaultAgents: [],   // loaded from /api/config/defaults
  libraryAgents: [],   // persistent agents in the library
  skills: [],          // built-in skill presets
  editingLibAgentId: null, // ID of the library agent being created/edited
};

// ── Simple Markdown Renderer ───────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  let html = text
    // Code blocks
    .replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
      return `<pre><code class="language-${lang || 'text'}">${escHtml(code.trimEnd())}</code></pre>`;
    })
    // Inline code
    .replace(/`([^`]+)`/g, (_, code) => `<code>${escHtml(code)}</code>`)
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // Unordered lists
    .replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
    // Ordered lists
    .replace(/^\s*\d+\. (.+)$/gm, '<li>$1</li>')
    // Paragraphs (double newline)
    .replace(/\n\n+/g, '</p><p>')
    // Single newlines
    .replace(/\n/g, '<br>');

  // Wrap in paragraph if not starting with a block element
  if (!html.startsWith('<h') && !html.startsWith('<pre') && !html.startsWith('<ul') && !html.startsWith('<ol')) {
    html = `<p>${html}</p>`;
  }
  return html;
}

function escHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Color Utilities ────────────────────────────────────────────
function hexToRgba(color, alpha) {
  // color can be hsl(...) or hex
  return color.replace(')', `, ${alpha})`).replace('hsl(', 'hsla(');
}

// ── Time Formatting ────────────────────────────────────────────
function formatTime(ts) {
  const d = ts ? new Date(ts * 1000) : new Date();
  return d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
}

// ── API helpers ────────────────────────────────────────────────
async function apiGet(path) {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function apiPost(path, data) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

async function apiPut(path, data) {
  const r = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${r.status}`);
  }
  return r.json();
}

async function apiDelete(path) {
  const r = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

// ── DOM References ─────────────────────────────────────────────
const $ = id => document.getElementById(id);

const els = {
  roomList: $('room-list'),
  emptyState: $('empty-state'),
  chatContainer: $('chat-container'),
  messagesArea: $('messages-area'),
  messageInput: $('message-input'),
  sendBtn: $('send-btn'),
  roomTitle: $('room-title'),
  agentPills: $('agent-pills'),
  connectionStatus: $('connection-status'),
  mentionHint: $('mention-hint'),

  // Modals
  modalRoom: $('modal-room'),
  modalRoomTitle: $('modal-room-title'),
  roomNameInput: $('room-name-input'),
  agentListEditor: $('agent-list-editor'),
  modalAgent: $('modal-agent'),
  agentNameInput: $('agent-name-input'),
  agentProviderSelect: $('agent-provider-select'),
  agentModelSelect: $('agent-model-select'),
  agentEmojiInput: $('agent-emoji-input'),
  agentApiKeyInput: $('agent-apikey-input'),
  agentSystemInput: $('agent-system-input'),
  agentSkillSelect: $('agent-skill-select'),
};

// ── Model defaults by provider ─────────────────────────────────
const PROVIDER_DEFAULTS = {
  gemini: { model: 'gemini-2.5-flash', emoji: '💎' },
  openai: { model: 'gpt-4o-mini', emoji: '🧠' },
  anthropic: { model: 'claude-3-5-haiku-20241022', emoji: '🌟' },
  openrouter: { model: 'google/gemini-2.5-flash', emoji: '🚀' },
  freemodel: { model: 'fre-5.5', emoji: '🚀' },
  litert_lm: { model: '', emoji: '⚙️' },
};

// ── Init ───────────────────────────────────────────────────────
async function init() {
  await loadDefaultAgents();
  await loadRooms();
  bindEvents();
  autoResizeTextarea();
}

async function loadDefaultAgents() {
  try {
    const data = await apiGet('/api/config/defaults');
    state.defaultAgents = data.default_agents || [];
  } catch (e) {
    console.warn('Could not load default agents:', e);
  }
}

// ── Rooms ──────────────────────────────────────────────────────
async function loadRooms() {
  try {
    state.rooms = await apiGet('/api/rooms');
    renderRoomList();
  } catch (e) {
    console.error('Failed to load rooms:', e);
  }
}

function renderRoomList() {
  els.roomList.innerHTML = '';
  if (state.rooms.length === 0) {
    els.roomList.innerHTML = `<li style="padding: 8px 12px; color: var(--text-muted); font-size: 12px;">Chưa có phòng nào</li>`;
    return;
  }
  for (const room of state.rooms) {
    const li = document.createElement('li');
    li.className = 'room-item' + (room.room_id === state.currentRoomId ? ' active' : '');
    li.dataset.roomId = room.room_id;
    const agentNames = room.agents.map(a => a.avatar_emoji + a.name).join(' · ');
    li.innerHTML = `
      <span class="room-item-icon">💬</span>
      <div class="room-item-info">
        <div class="room-item-name">${escHtml(room.name)}</div>
        <div class="room-item-agents">${escHtml(agentNames)}</div>
      </div>
    `;
    li.addEventListener('click', () => openRoom(room.room_id));
    els.roomList.appendChild(li);
  }
}

async function openRoom(roomId) {
  if (state.currentRoomId === roomId) return;

  // Disconnect previous WS
  disconnectWs();

  state.currentRoomId = roomId;
  const room = state.rooms.find(r => r.room_id === roomId);
  if (!room) return;

  // Update UI
  els.emptyState.style.display = 'none';
  els.chatContainer.style.display = 'flex';
  els.chatContainer.style.flexDirection = 'column';
  els.roomTitle.textContent = room.name;
  state.agents = room.agents;

  // Recalculate input height now that it is visible
  autoResizeTextarea();


  renderAgentPills(room.agents);
  renderRoomList();

  // Clear messages
  els.messagesArea.innerHTML = '';
  state.activeStreams = {};
  state.typingIndicators = {};

  // Load history
  try {
    const history = await apiGet(`/api/rooms/${roomId}/history`);
    for (const msg of history) {
      if (msg.role === 'user') {
        appendUserMessage(msg.content, msg.timestamp);
      } else if (msg.role === 'agent') {
        const agent = room.agents.find(a => a.name === msg.agent_name) || {
          name: msg.agent_name,
          provider: msg.provider,
          avatar_emoji: '🤖',
          color: 'hsl(220, 70%, 60%)',
        };
        appendAgentMessage(agent, msg.content, msg.timestamp, false);
      }
    }
    scrollToBottom();
  } catch (e) {
    console.error('Failed to load history:', e);
  }

  // Connect WebSocket
  connectWs(roomId);
}

// ── Agent Pills ────────────────────────────────────────────────
function renderAgentPills(agents) {
  els.agentPills.innerHTML = '';
  for (const agent of agents) {
    const pill = document.createElement('span');
    pill.className = 'agent-pill';
    pill.id = `pill-${agent.name}`;
    pill.style.color = agent.color;
    pill.style.borderColor = hexToRgba(agent.color, 0.3);
    pill.style.background = hexToRgba(agent.color, 0.08);
    pill.innerHTML = `${agent.avatar_emoji} ${escHtml(agent.name)}`;
    els.agentPills.appendChild(pill);
  }
}

function setAgentPillTyping(agentName, isTyping) {
  const pill = document.getElementById(`pill-${agentName}`);
  if (pill) pill.classList.toggle('typing', isTyping);
}

// ── WebSocket ──────────────────────────────────────────────────
function connectWs(roomId) {
  setConnectionStatus('connecting');
  const ws = new WebSocket(`${WS_BASE}/ws/${roomId}`);
  state.ws = ws;

  ws.onopen = () => {
    setConnectionStatus('connected');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWsMessage(msg);
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };

  ws.onclose = () => {
    setConnectionStatus('disconnected');
    // Auto-reconnect after 3s
    if (state.currentRoomId === roomId) {
      setTimeout(() => {
        if (state.currentRoomId === roomId) connectWs(roomId);
      }, 3000);
    }
  };

  ws.onerror = () => setConnectionStatus('disconnected');
}

function disconnectWs() {
  if (state.ws) {
    state.ws.onclose = null; // prevent auto-reconnect
    state.ws.close();
    state.ws = null;
  }
  state.currentRoomId = null;
}

function sendWsMessage(content) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: 'message', content }));
    return true;
  }
  return false;
}

function setConnectionStatus(status) {
  const dot = els.connectionStatus.querySelector('.status-dot');
  dot.className = `status-dot ${status}`;
  const labels = { connected: 'Đã kết nối', connecting: 'Đang kết nối...', disconnected: 'Mất kết nối' };
  els.connectionStatus.childNodes[1] && (els.connectionStatus.childNodes[1].textContent = ' ' + labels[status]);
  els.connectionStatus.innerHTML = `<span class="status-dot ${status}"></span> ${labels[status]}`;
}

// ── Handle WS Messages ─────────────────────────────────────────
function updateAgentState(agentData) {
  const idx = state.agents.findIndex(a => a.name === agentData.name);
  if (idx !== -1) {
    state.agents[idx] = agentData;
    // Optionally re-render pills if needed, but not strictly required unless we show model name
  }
}

function handleWsMessage(msg) {
  switch (msg.type) {
    case 'room_info': {
      const targetRoom = state.rooms.find(r => r.room_id === msg.room_id);
      if (targetRoom) {
        targetRoom.name = msg.name;
        targetRoom.agents = msg.agents;
      } else {
        state.rooms.push({
          room_id: msg.room_id,
          name: msg.name,
          agents: msg.agents
        });
      }
      renderRoomList();
      if (state.currentRoomId === msg.room_id) {
        els.roomTitle.textContent = msg.name;
        state.agents = msg.agents;
        renderAgentPills(msg.agents);
      }
      break;
    }

    case 'user_message': {
      const lastMsgEl = els.messagesArea.lastElementChild;
      if (lastMsgEl && lastMsgEl.classList.contains('user-message')) {
        const bubble = lastMsgEl.querySelector('.message-bubble');
        if (bubble && bubble.textContent.trim() === msg.content.trim()) {
          const timeEl = lastMsgEl.querySelector('.message-time');
          if (timeEl && msg.timestamp) {
            timeEl.textContent = formatTime(msg.timestamp);
          }
          break;
        }
      }
      appendUserMessage(msg.content, msg.timestamp);
      break;
    }

    case 'agent_typing':
      updateAgentState(msg.agent);
      showTypingIndicator(msg.agent);
      setAgentPillTyping(msg.agent.name, true);
      break;

    case 'agent_token':
      handleAgentToken(msg.agent, msg.token, msg.is_debate);
      break;

    case 'agent_done':
      updateAgentState(msg.agent);
      finalizeAgentMessage(msg.agent, msg.full_response, msg.is_debate);
      break;

    case 'agent_retrying':
      updateAgentState(msg.agent);
      removeTypingIndicator(msg.agent.name);
      setAgentPillTyping(msg.agent.name, false);
      // Remove any partial stream
      removeExistingStream(msg.agent.name);
      appendSystemMessage(
        `🔄 ${msg.error}`
      );
      break;

    case 'agent_error':
      updateAgentState(msg.agent);
      removeTypingIndicator(msg.agent.name);
      setAgentPillTyping(msg.agent.name, false);
      appendAgentError(msg.agent, msg.error, msg.retryable);
      break;

    case 'error':
      appendSystemMessage(`⚠️ ${msg.message}`);
      break;

    case 'agent_removed':
      // Remove agent from local state
      state.agents = state.agents.filter(a => a.name !== msg.agent_name);
      renderAgentPills(state.agents);
      
      // Update room list state
      const room = state.rooms.find(r => r.room_id === state.currentRoomId);
      if (room) room.agents = state.agents;
      renderRoomList();

      // Show a system message with a red banner style
      const removedMsg = document.createElement('div');
      removedMsg.className = 'system-message error-message';
      removedMsg.style.color = '#ef4444';
      removedMsg.style.background = 'rgba(239, 68, 68, 0.1)';
      removedMsg.style.border = '1px solid rgba(239, 68, 68, 0.2)';
      removedMsg.style.padding = '12px';
      removedMsg.style.borderRadius = '8px';
      removedMsg.innerHTML = `⚠️ <b>Hệ thống:</b> Đã loại <b>${escHtml(msg.agent_name)}</b> khỏi phòng. Lý do: ${escHtml(msg.reason)}`;
      els.messagesArea.appendChild(removedMsg);
      scrollToBottom();
      break;

    case 'pong':
      break;
  }
}

// ── Typing Indicator ───────────────────────────────────────────
function showTypingIndicator(agent) {
  if (state.typingIndicators[agent.name]) return;

  removeExistingStream(agent.name);

  const el = document.createElement('div');
  el.className = 'typing-indicator';
  el.id = `typing-${agent.name}`;
  el.innerHTML = `
    <div class="avatar" style="background: ${hexToRgba(agent.color, 0.15)}; border-color: ${hexToRgba(agent.color, 0.4)};">
      ${agent.avatar_emoji}
    </div>
    <div>
      <div class="typing-dots">
        <div class="typing-dot" style="background: ${agent.color}"></div>
        <div class="typing-dot" style="background: ${agent.color}"></div>
        <div class="typing-dot" style="background: ${agent.color}"></div>
      </div>
      <div class="typing-agent-name">${escHtml(agent.name)} đang trả lời...</div>
    </div>
  `;
  els.messagesArea.appendChild(el);
  state.typingIndicators[agent.name] = el;
  scrollToBottom();
}

function removeTypingIndicator(agentName) {
  const el = state.typingIndicators[agentName];
  if (el) {
    el.remove();
    delete state.typingIndicators[agentName];
  }
}

// ── Agent Token Streaming ──────────────────────────────────────
function handleAgentToken(agent, token, isDebate) {
  // Remove typing indicator, start or continue stream bubble
  removeTypingIndicator(agent.name);

  if (!state.activeStreams[agent.name]) {
    // Create new message bubble for streaming
    const { msgEl, textEl } = createStreamingMessage(agent, isDebate);
    state.activeStreams[agent.name] = { msgEl, textEl, rawText: '' };
  }

  const stream = state.activeStreams[agent.name];
  stream.rawText += token;

  // Update displayed text with markdown
  stream.textEl.innerHTML = renderMarkdown(stream.rawText) + '<span class="streaming-cursor"></span>';
  scrollToBottom();
}

function createStreamingMessage(agent, isDebate) {
  const msgEl = document.createElement('div');
  msgEl.className = `message agent-message${isDebate ? ' debate-message' : ''}`;
  msgEl.id = `stream-${agent.name}`;

  const timeStr = formatTime(null);
  const providerLabel = agent.provider || '';

  msgEl.innerHTML = `
    <div class="avatar" style="background: ${hexToRgba(agent.color, 0.15)}; border-color: ${hexToRgba(agent.color, 0.4)};">
      ${agent.avatar_emoji}
    </div>
    <div class="message-content-wrapper">
      ${isDebate ? `<div class="debate-indicator">🔄 Bổ sung / phản bác</div>` : ''}
      <div class="message-header">
        <span class="message-sender" style="color: ${agent.color}">${escHtml(agent.name)}</span>
        <span class="message-provider-badge">${providerLabel}</span>
        <span class="message-time">${timeStr}</span>
      </div>
      <div class="message-bubble">
        <span class="message-text"></span>
      </div>
    </div>
  `;

  els.messagesArea.appendChild(msgEl);
  const textEl = msgEl.querySelector('.message-text');
  return { msgEl, textEl };
}

function finalizeAgentMessage(agent, fullResponse, isDebate) {
  removeTypingIndicator(agent.name);
  setAgentPillTyping(agent.name, false);

  const stream = state.activeStreams[agent.name];
  if (stream) {
    // Remove streaming cursor, render final markdown
    stream.textEl.innerHTML = renderMarkdown(fullResponse || stream.rawText);
    delete state.activeStreams[agent.name];
  } else if (fullResponse && fullResponse !== '[SKIP]') {
    // Message came without streaming (fallback)
    appendAgentMessage(agent, fullResponse, null, isDebate);
  }
  scrollToBottom();
}

function removeExistingStream(agentName) {
  const existing = document.getElementById(`stream-${agentName}`);
  if (existing) existing.remove();
  delete state.activeStreams[agentName];
}

// ── Append Messages ────────────────────────────────────────────
function appendUserMessage(content, timestamp) {
  const el = document.createElement('div');
  el.className = 'message user-message';
  el.innerHTML = `
    <div class="avatar user-avatar">U</div>
    <div class="message-content-wrapper">
      <div class="message-header">
        <span class="message-sender" style="color: var(--accent)">Bạn</span>
        <span class="message-time">${formatTime(timestamp)}</span>
      </div>
      <div class="message-bubble">${renderMarkdown(content)}</div>
    </div>
  `;
  els.messagesArea.appendChild(el);
  scrollToBottom();
}

function appendAgentMessage(agent, content, timestamp, isDebate) {
  if (content === '[SKIP]') return;
  const el = document.createElement('div');
  el.className = `message agent-message${isDebate ? ' debate-message' : ''}`;
  el.innerHTML = `
    <div class="avatar" style="background: ${hexToRgba(agent.color, 0.15)}; border-color: ${hexToRgba(agent.color, 0.4)};">
      ${agent.avatar_emoji}
    </div>
    <div class="message-content-wrapper">
      ${isDebate ? `<div class="debate-indicator">🔄 Bổ sung / phản bác</div>` : ''}
      <div class="message-header">
        <span class="message-sender" style="color: ${agent.color}">${escHtml(agent.name)}</span>
        <span class="message-provider-badge">${agent.provider || ''}</span>
        <span class="message-time">${formatTime(timestamp)}</span>
      </div>
      <div class="message-bubble">${renderMarkdown(content)}</div>
    </div>
  `;
  els.messagesArea.appendChild(el);
}

function appendSystemMessage(text) {
  const el = document.createElement('div');
  el.className = 'date-divider';
  el.innerHTML = `<span class="date-divider-text">${escHtml(text)}</span>`;
  els.messagesArea.appendChild(el);
  scrollToBottom();
}

function appendAgentError(agent, error, retryable) {
  const el = document.createElement('div');
  el.className = 'agent-error-banner';
  const color = agent.color || 'hsl(0, 70%, 60%)';

  el.innerHTML = `
    <div class="agent-error-content">
      <span class="agent-error-icon">❌</span>
      <div class="agent-error-info">
        <span class="agent-error-name" style="color:${color}">${escHtml(agent.name || agent.avatar_emoji)}</span>
        <span class="agent-error-msg">${escHtml(error)}</span>
      </div>
      ${retryable ? `
        <button class="btn-retry" data-agent="${escHtml(agent.name)}" title="Thử lại">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="23 4 23 10 17 10"></polyline>
            <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
          </svg>
          Thử lại
        </button>
      ` : ''}
    </div>
  `;

  if (retryable) {
    const btn = el.querySelector('.btn-retry');
    btn.addEventListener('click', () => {
      retryAgent(agent.name);
      // Disable button after click to prevent spam
      btn.disabled = true;
      btn.innerHTML = `
        <svg class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <path d="M21 12a9 9 0 11-6.219-8.56"></path>
        </svg>
        Đang thử...
      `;
      // Remove error banner after a delay
      setTimeout(() => el.remove(), 1500);
    });
  }

  els.messagesArea.appendChild(el);
  scrollToBottom();
}

function retryAgent(agentName) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({
      type: 'retry_agent',
      agent_name: agentName,
    }));
  }
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    els.messagesArea.scrollTop = els.messagesArea.scrollHeight;
  });
}

// ── Send Message ───────────────────────────────────────────────
function sendMessage() {
  const content = els.messageInput.value.trim();
  if (!content || !state.currentRoomId) return;

  // Optimistically append user message
  appendUserMessage(content, null);

  // Send via WebSocket
  const sent = sendWsMessage(content);
  if (!sent) {
    appendSystemMessage('⚠️ Không thể gửi — WebSocket chưa kết nối');
    return;
  }

  els.messageInput.value = '';
  els.sendBtn.disabled = true;
  hideMentionHint();
  autoResizeTextarea();
}

// ── Mention detection ──────────────────────────────────────────
function checkMentions(text) {
  const lastAtIdx = text.lastIndexOf('@');
  if (lastAtIdx === -1) { hideMentionHint(); return; }

  const partial = text.slice(lastAtIdx + 1).toLowerCase();
  const matched = state.agents.filter(a =>
    a.name.toLowerCase().startsWith(partial)
  );

  if (matched.length === 0) { hideMentionHint(); return; }

  els.mentionHint.innerHTML = matched.map(a => `
    <span class="mention-chip"
      style="color:${a.color}; border-color:${hexToRgba(a.color,0.3)}; background:${hexToRgba(a.color,0.08)};"
      data-name="${escHtml(a.name)}">
      ${a.avatar_emoji} @${escHtml(a.name)}
    </span>
  `).join('');

  els.mentionHint.style.display = 'flex';

  els.mentionHint.querySelectorAll('.mention-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const name = chip.dataset.name;
      const val = els.messageInput.value;
      const at = val.lastIndexOf('@');
      els.messageInput.value = val.slice(0, at) + `@${name} `;
      hideMentionHint();
      els.messageInput.focus();
      updateSendBtn();
    });
  });
}

function hideMentionHint() {
  els.mentionHint.style.display = 'none';
}

// ── Input events ───────────────────────────────────────────────
function updateSendBtn() {
  els.sendBtn.disabled = !els.messageInput.value.trim() || !state.currentRoomId;
}

function autoResizeTextarea() {
  const ta = els.messageInput;
  if (!ta) return;
  ta.style.height = 'auto';
  if (ta.scrollHeight > 0) {
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  } else {
    ta.style.height = '24px';
  }
}

// ── Room Modal ─────────────────────────────────────────────────
// ── Room Modal ─────────────────────────────────────────────────
function openCreateRoomModal() {
  state.isEditingRoom = false;
  state.editingAgentIndex = null;
  state.tempAgents = state.defaultAgents.length > 0
    ? JSON.parse(JSON.stringify(state.defaultAgents))
    : [];
  els.roomNameInput.value = '';
  els.modalRoomTitle.textContent = 'Tạo phòng mới';
  $('btn-save-room').textContent = 'Tạo phòng';
  $('btn-save-room').onclick = null;
  renderAgentEditor();
  els.modalRoom.style.display = 'flex';
  setTimeout(() => els.roomNameInput.focus(), 100);
}

function closeRoomModal() {
  els.modalRoom.style.display = 'none';
}

function renderAgentEditor() {
  els.agentListEditor.innerHTML = '';
  for (let i = 0; i < state.tempAgents.length; i++) {
    const agent = state.tempAgents[i];
    const color = generateColor(agent.name);
    const card = document.createElement('div');
    card.className = 'agent-card-editor';
    card.innerHTML = `
      <div class="agent-card-avatar" style="background:${hexToRgba(color,0.15)}; border-color:${hexToRgba(color,0.4)}">
        ${agent.avatar_emoji || '🤖'}
      </div>
      <div class="agent-card-info">
        <div class="agent-card-name" style="color:${color}">${escHtml(agent.name)}</div>
        <div class="agent-card-meta">${agent.provider} · ${agent.model || 'default'}</div>
      </div>
      <div class="agent-card-actions">
        <button class="agent-card-edit" data-idx="${i}" title="Sửa agent">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
            <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
          </svg>
        </button>
        <button class="agent-card-remove" data-idx="${i}" title="Xóa agent">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>
    `;
    card.querySelector('.agent-card-edit').addEventListener('click', (e) => {
      const idx = parseInt(e.currentTarget.dataset.idx);
      openEditAgentModal(idx);
    });
    card.querySelector('.agent-card-remove').addEventListener('click', (e) => {
      const idx = parseInt(e.currentTarget.dataset.idx);
      state.tempAgents.splice(idx, 1);
      renderAgentEditor();
    });
    els.agentListEditor.appendChild(card);
  }
}

async function saveRoom() {
  const name = els.roomNameInput.value.trim();
  if (!name) { els.roomNameInput.focus(); return; }
  if (state.tempAgents.length === 0) {
    alert('Vui lòng thêm ít nhất 1 Agent.'); return;
  }

  try {
    if (state.isEditingRoom) {
      const room = await apiPut(`/api/rooms/${state.currentRoomId}`, { name, agents: state.tempAgents });
      const idx = state.rooms.findIndex(r => r.room_id === state.currentRoomId);
      if (idx !== -1) {
        state.rooms[idx] = {
          room_id: room.room_id,
          name: room.name,
          agents: room.agents,
        };
      }
      els.roomTitle.textContent = room.name;
      state.agents = room.agents;
      renderAgentPills(room.agents);
      renderRoomList();
      closeRoomModal();
      showToast('✅ Đã cập nhật cấu hình phòng thành công!');
    } else {
      const room = await apiPost('/api/rooms', { name, agents: state.tempAgents });
      state.rooms.unshift({
        room_id: room.room_id,
        name: room.name,
        agents: room.agents,
      });
      renderRoomList();
      closeRoomModal();
      openRoom(room.room_id);
    }
  } catch (e) {
    alert((state.isEditingRoom ? 'Lỗi cập nhật phòng: ' : 'Lỗi tạo phòng: ') + e.message);
  }
}

async function deleteCurrentRoom() {
  if (!state.currentRoomId) return;
  const room = state.rooms.find(r => r.room_id === state.currentRoomId);
  if (!confirm(`Xóa phòng "${room?.name}"?`)) return;

  try {
    await apiDelete(`/api/rooms/${state.currentRoomId}`);
    state.rooms = state.rooms.filter(r => r.room_id !== state.currentRoomId);
    disconnectWs();
    state.currentRoomId = null;
    els.chatContainer.style.display = 'none';
    els.emptyState.style.display = 'flex';
    renderRoomList();
  } catch (e) {
    alert('Lỗi xóa phòng: ' + e.message);
  }
}

// ── Agent Modal ────────────────────────────────────────────────
function openAddAgentModal() {
  state.editingAgentIndex = null;
  state.pendingAgentConfig = null;
  els.agentNameInput.value = '';
  els.agentProviderSelect.value = 'gemini';
  els.agentEmojiInput.value = '';
  els.agentApiKeyInput.value = '';
  els.agentSystemInput.value = '';

  els.agentSkillSelect.innerHTML = '<option value="">-- Tùy chỉnh (Không dùng skill) --</option>';
  state.skills.forEach(skill => {
    const opt = document.createElement('option');
    opt.value = skill.name;
    opt.textContent = skill.name;
    els.agentSkillSelect.appendChild(opt);
  });

  if (state.skills.length > 0) {
    const defaultSkill = state.skills[0];
    els.agentSkillSelect.value = defaultSkill.name;
    els.agentSystemInput.value = defaultSkill.system_prompt;
  } else {
    els.agentSkillSelect.value = '';
  }

  const inputEl = $('agent-model-input');
  if (inputEl) inputEl.value = '';
  updateAgentModelsDropdown();
  els.modalAgent.style.display = 'flex';
  setTimeout(() => els.agentNameInput.focus(), 100);
}

async function openEditAgentModal(idx) {
  state.editingAgentIndex = idx;
  const agent = state.tempAgents[idx];
  
  els.agentNameInput.value = agent.name || '';
  els.agentProviderSelect.value = agent.provider || 'gemini';
  els.agentEmojiInput.value = agent.avatar_emoji || '';
  els.agentApiKeyInput.value = agent.api_key || '';
  els.agentSystemInput.value = agent.system_prompt || '';

  els.agentSkillSelect.innerHTML = '<option value="">-- Tùy chỉnh (Không dùng skill) --</option>';
  state.skills.forEach(skill => {
    const opt = document.createElement('option');
    opt.value = skill.name;
    opt.textContent = skill.name;
    els.agentSkillSelect.appendChild(opt);
  });
  els.agentSkillSelect.value = agent.skill || '';

  await updateAgentModelsDropdown();
  if (agent.provider === 'litert_lm') {
    const inputEl = $('agent-model-input');
    if (inputEl) inputEl.value = agent.model || '';
  } else {
    els.agentModelSelect.value = agent.model || '';
  }
  
  els.modalAgent.style.display = 'flex';
  setTimeout(() => els.agentNameInput.focus(), 100);
}

function closeAgentModal() {
  els.modalAgent.style.display = 'none';
}

async function updateAgentModelsDropdown() {
  const provider = els.agentProviderSelect.value;
  const def = PROVIDER_DEFAULTS[provider] || {};

  // Update placeholder for emoji if not custom
  if (!els.agentEmojiInput.value) {
    els.agentEmojiInput.placeholder = def.emoji || '🤖';
  }

  const inputEl = $('agent-model-input');
  if (provider === 'litert_lm') {
    els.agentModelSelect.style.display = 'none';
    if (inputEl) inputEl.style.display = 'block';
    return;
  } else {
    els.agentModelSelect.style.display = 'block';
    if (inputEl) inputEl.style.display = 'none';
  }

  // Clear dropdown options and show a loading placeholder
  els.agentModelSelect.innerHTML = '<option value="">Đang tải danh sách models...</option>';
  els.agentModelSelect.disabled = true;

  try {
    const models = await apiGet(`/api/models/${provider}`);
    els.agentModelSelect.innerHTML = '';
    
    if (provider === 'openrouter') {
      const freeModels = models.filter(m => m.endsWith(':free'));
      const paidModels = models.filter(m => !m.endsWith(':free'));
      
      if (freeModels.length > 0) {
        const groupFree = document.createElement('optgroup');
        groupFree.label = '🆓 Miễn phí (Free)';
        for (const model of freeModels) {
          const opt = document.createElement('option');
          opt.value = model;
          opt.textContent = model;
          if (model === def.model) opt.selected = true;
          groupFree.appendChild(opt);
        }
        els.agentModelSelect.appendChild(groupFree);
      }
      
      if (paidModels.length > 0) {
        const groupPaid = document.createElement('optgroup');
        groupPaid.label = '💰 Trả phí (Paid)';
        for (const model of paidModels) {
          const opt = document.createElement('option');
          opt.value = model;
          opt.textContent = model;
          if (model === def.model) opt.selected = true;
          groupPaid.appendChild(opt);
        }
        els.agentModelSelect.appendChild(groupPaid);
      }
    } else if (provider === 'gemini' && models.length > 5) {
      // Group Gemini models by generation
      const groups = {
        '🚀 Gemini 3.x': [],
        '⚡ Gemini 2.5': [],
        '💎 Gemini 2.0': [],
        '🔷 Gemini 1.x': [],
        '🧩 Gemma': [],
        '🔹 Khác': [],
      };
      for (const model of models) {
        if (model.startsWith('gemma-')) groups['🧩 Gemma'].push(model);
        else if (/^gemini-3/.test(model)) groups['🚀 Gemini 3.x'].push(model);
        else if (/^gemini-2\.5/.test(model)) groups['⚡ Gemini 2.5'].push(model);
        else if (/^gemini-2\.0/.test(model)) groups['💎 Gemini 2.0'].push(model);
        else if (/^gemini-1/.test(model)) groups['🔷 Gemini 1.x'].push(model);
        else groups['🔹 Khác'].push(model);
      }
      for (const [label, list] of Object.entries(groups)) {
        if (list.length === 0) continue;
        const grp = document.createElement('optgroup');
        grp.label = label;
        for (const model of list) {
          const opt = document.createElement('option');
          opt.value = model;
          opt.textContent = model;
          if (model === def.model) opt.selected = true;
          grp.appendChild(opt);
        }
        els.agentModelSelect.appendChild(grp);
      }
    } else {
      for (const model of models) {
        const opt = document.createElement('option');
        opt.value = model;
        opt.textContent = model;
        if (model === def.model) {
          opt.selected = true;
        }
        els.agentModelSelect.appendChild(opt);
      }
    }
  } catch (e) {
    console.warn(`Failed to fetch models for ${provider}:`, e);
    // Fallback to provider default if API fails
    els.agentModelSelect.innerHTML = `<option value="${def.model || ''}" selected>${def.model || ''} (mặc định)</option>`;
  } finally {
    els.agentModelSelect.disabled = false;
  }
}

function saveAgent() {
  const name = els.agentNameInput.value.trim();
  if (!name) { els.agentNameInput.focus(); return; }

  const provider = els.agentProviderSelect.value;
  const def = PROVIDER_DEFAULTS[provider] || {};

  const modelValue = provider === 'litert_lm'
    ? ($('agent-model-input') ? $('agent-model-input').value.trim() : '')
    : els.agentModelSelect.value || def.model || '';

  const agentConfig = {
    name,
    provider,
    model: modelValue,
    avatar_emoji: els.agentEmojiInput.value.trim() || def.emoji || '🤖',
    api_key: els.agentApiKeyInput.value.trim(),
    system_prompt: els.agentSystemInput.value.trim(),
    skill: els.agentSkillSelect.value || null,
  };

  if (state.editingAgentIndex !== null && state.editingAgentIndex !== undefined) {
    state.tempAgents[state.editingAgentIndex] = agentConfig;
  } else {
    state.tempAgents.push(agentConfig);
  }
  renderAgentEditor();
  closeAgentModal();
}


// ── Color generator (same as backend) ─────────────────────────
function generateColor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash) + name.charCodeAt(i);
    hash = hash & hash;
  }
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 70%, 60%)`;
}

// ── Settings Panel ─────────────────────────────────────────────
async function openSettings() {
  const redirectUri = `${window.location.origin}/api/auth/google/callback`;
  const el = document.getElementById('redirect-uri-display');
  if (el) el.textContent = redirectUri;

  await refreshSettingsStatus();
  document.getElementById('modal-settings').style.display = 'flex';
}

function closeSettings() {
  document.getElementById('modal-settings').style.display = 'none';
}

async function refreshSettingsStatus() {
  try {
    const status = await apiGet('/api/settings/status');
    updateProviderUI('gemini', status.gemini);
    updateProviderUI('openai', status.openai);
    updateProviderUI('anthropic', status.anthropic);
    updateProviderUI('openrouter', status.openrouter);
    updateProviderUI('freemodel', status.freemodel);

    // Update credential files status badges
    updateFilesUI(status.files);

    if (status.freemodel?.base_url) {
      const el = document.getElementById('freemodel-base-url-input');
      if (el) el.placeholder = status.freemodel.base_url;
    }

    const configuredCount = ['gemini','openai','anthropic','openrouter','freemodel'].filter(p => status[p]?.method).length;
    updateSidebarAuthDot(configuredCount);


  } catch (e) {
    console.warn('Could not load settings status:', e);
  }
}

function updateProviderUI(provider, status) {
  if (!status) return;
  const badge = document.getElementById(`${provider}-badge`);
  const statusText = document.getElementById(`${provider}-status-text`);
  if (!badge || !statusText) return;

  if (status.method === 'oauth') {
    badge.textContent = 'OAuth ✓';
    badge.className = 'provider-badge connected';
    statusText.textContent = 'Đã đăng nhập Google OAuth';
  } else if (status.method === 'api_key') {
    badge.textContent = 'API Key ✓';
    badge.className = 'provider-badge api-key';
    statusText.textContent = 'Đã cấu hình API Key';
  } else {
    badge.textContent = 'Chưa cấu hình';
    badge.className = 'provider-badge not-set';
    statusText.textContent = 'Cần API key hoặc OAuth login';
  }
}




function updateSidebarAuthDot(configuredCount) {
  let dot = document.querySelector('.sidebar-footer-btn .auth-dot');
  if (!dot) {
    const btn = document.getElementById('btn-settings');
    if (btn) {
      dot = document.createElement('span');
      dot.className = 'auth-dot';
      btn.appendChild(dot);
    }
  }
  if (!dot) return;
  dot.className = `auth-dot ${configuredCount >= 3 ? 'all-ok' : configuredCount > 0 ? 'partial' : 'none'}`;
}

async function saveApiKey(provider, inputId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const key = input.value.trim();
  try {
    await apiPost('/api/settings/api-key', { provider, api_key: key });
    input.value = '';
    input.placeholder = key ? '••••••••••••••• (saved)' : '(cleared)';
    await refreshSettingsStatus();
    showToast(key ? `✅ ${provider} API key đã lưu!` : `🗑 ${provider} API key đã xóa`);
  } catch (e) {
    showToast(`❌ Lỗi: ${e.message}`, 'error');
  }
}

async function clearApiKey(provider, inputId) {
  const input = document.getElementById(inputId);
  if (input) input.value = '';
  try {
    await fetch(`${API_BASE}/api/settings/api-key/${provider}`, { method: 'DELETE' });
    await refreshSettingsStatus();
    showToast(`🗑 ${provider} API key đã xóa`);
  } catch (e) {
    showToast(`❌ Lỗi: ${e.message}`, 'error');
  }
}



// ── Toast Notifications ────────────────────────────────────────
function showToast(message, type = 'success') {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed; bottom: 24px; right: 24px; z-index: 9999;
    padding: 12px 20px; border-radius: 10px; font-size: 14px;
    font-weight: 500; max-width: 360px; word-break: break-word;
    animation: slideUp 0.3s ease;
    background: ${type === 'error' ? 'rgba(248,113,113,0.15)' : 'rgba(74,222,128,0.15)'};
    border: 1px solid ${type === 'error' ? 'rgba(248,113,113,0.4)' : 'rgba(74,222,128,0.4)'};
    color: ${type === 'error' ? '#f87171' : '#4ade80'};
    backdrop-filter: blur(10px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  `;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3500);
}

// ── Library Slide-Over Panel Logic ────────────────────────────
async function openLibrary() {
  $('library-panel-overlay').style.display = 'block';
  $('library-panel').classList.add('open');
  state.activeLibraryTab = 'agents';
  showLibraryTab('agents');
  await loadLibraryAgents();
}

function closeLibrary() {
  $('library-panel').classList.remove('open');
  $('library-panel-overlay').style.display = 'none';
}

function showLibraryTab(tab) {
  state.activeLibraryTab = tab;
  document.querySelectorAll('.library-panel-tabs .lib-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  if (tab === 'agents') {
    $('lib-panel-agents').style.display = 'block';
    $('lib-panel-skills').style.display = 'none';
  } else {
    $('lib-panel-agents').style.display = 'none';
    $('lib-panel-skills').style.display = 'block';
    loadSkills();
  }
}

async function loadLibraryAgents() {
  const grid = $('lib-agent-grid');
  grid.innerHTML = '<div class="lib-empty-state">Đang tải danh sách agents...</div>';
  try {
    const data = await apiGet('/api/library/agents');
    state.libraryAgents = data.agents || [];
    renderLibraryAgents();
  } catch (e) {
    grid.innerHTML = `<div class="lib-empty-state">❌ Không thể tải danh sách agents: ${e.message}</div>`;
  }
}

function renderLibraryAgents() {
  const grid = $('lib-agent-grid');
  grid.innerHTML = '';
  const query = $('lib-search').value.toLowerCase().trim();
  
  // 1. Index library overrides (e.g. customized default agents)
  const overrides = {};
  const customAgents = [];
  for (const a of state.libraryAgents) {
    if (a.id && a.id.startsWith('default-')) {
      overrides[a.id] = a;
    } else {
      customAgents.push(a);
    }
  }

  // 2. Map default agents, replacing if overridden
  const defaults = state.defaultAgents.map(a => {
    const id = `default-${a.name.toLowerCase()}`;
    const isCustomized = !!overrides[id];
    const agentData = isCustomized ? overrides[id] : a;
    return {
      ...agentData,
      id,
      is_default: true,
      is_customized: isCustomized,
      description: agentData.description || `Agent mặc định của hệ thống (${agentData.provider}).`
    };
  });

  // 3. Combine both lists
  const allAgents = [...defaults, ...customAgents];

  const filtered = allAgents.filter(a => {
    return a.name.toLowerCase().includes(query) || 
           (a.description && a.description.toLowerCase().includes(query)) ||
           a.provider.toLowerCase().includes(query) ||
           a.model.toLowerCase().includes(query);
  });

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="lib-empty-state">
        <div class="lib-empty-state-icon">🗂</div>
        <p>${query ? 'Không tìm thấy agent phù hợp' : 'Kho Agent trống. Hãy tạo agent đầu tiên!'}</p>
      </div>
    `;
    return;
  }

  for (const agent of filtered) {
    const card = document.createElement('div');
    card.className = 'lib-agent-card';
    card.dataset.id = agent.id;
    
    const color = generateColor(agent.name);
    
    card.innerHTML = `
      <div class="lib-agent-card-row">
        <div class="lib-agent-avatar" style="background: ${hexToRgba(color, 0.15)}; border-color: ${color}; color: ${color}">
          ${agent.avatar_emoji || '🤖'}
        </div>
        <div class="lib-agent-info">
          <div class="lib-agent-name">
            ${escHtml(agent.name)}
            ${agent.is_default ? `<span class="default-badge" style="font-size:10px;padding:1px 5px;border-radius:4px;font-weight:400;background:${agent.is_customized ? 'rgba(108,111,255,0.15)' : 'rgba(255,255,255,0.08)'};color:${agent.is_customized ? 'var(--accent)' : 'var(--text-muted)'};margin-left:4px">${agent.is_customized ? 'Đã sửa' : 'Mặc định'}</span>` : ''}
          </div>
          <div class="lib-agent-meta">
            <span class="lib-agent-provider-badge">${agent.provider}</span>
            <span style="word-break:break-all">${escHtml(agent.model)}</span>
          </div>
        </div>
        <button class="lib-add-to-room-btn" data-id="${agent.id}">+ Thêm</button>
      </div>
      <div class="lib-agent-desc">${escHtml(agent.description || 'Không có mô tả.')}</div>
      <div class="lib-agent-card-bottom">
        <div class="lib-agent-status" id="status-container-${agent.id}" title="Click để kiểm tra trạng thái">
          <span class="lib-status-dot idle" id="dot-${agent.id}"></span>
          <span id="txt-${agent.id}" style="font-size:11px;color:var(--text-secondary)">Chưa test</span>
          <span class="lib-token-info" id="tokens-${agent.id}" style="display:none"></span>
        </div>
        <div class="lib-agent-actions">
          ${agent.is_default ? `
            <button class="lib-btn lib-edit-btn" data-id="${agent.id}">✏️</button>
            ${agent.is_customized ? `<button class="lib-btn lib-btn-danger lib-restore-btn" data-id="${agent.id}">🔄</button>` : `<button class="lib-btn lib-duplicate-btn" data-id="${agent.id}">📋</button>`}
          ` : `
            <button class="lib-btn lib-edit-btn" data-id="${agent.id}">✏️</button>
            <button class="lib-btn lib-duplicate-btn" data-id="${agent.id}">📋</button>
            <button class="lib-btn lib-btn-danger lib-delete-btn" data-id="${agent.id}">🗑</button>
          `}
        </div>
      </div>
    `;

    // Bind card actions
    card.querySelector('.lib-add-to-room-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      addLibraryAgentToRoom(agent);
    });
    
    card.querySelector('.lib-edit-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      openLibAgentModal(agent);
    });

    if (agent.is_default && agent.is_customized) {
      card.querySelector('.lib-restore-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteLibAgent(agent.id, agent.name);
      });
    } else if (!agent.is_default) {
      card.querySelector('.lib-delete-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteLibAgent(agent.id, agent.name);
      });
    }

    const dupBtn = card.querySelector('.lib-duplicate-btn');
    if (dupBtn) {
      dupBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        duplicateLibAgent(agent.id);
      });
    }

    card.querySelector('.lib-agent-status').addEventListener('click', (e) => {
      e.stopPropagation();
      testSingleAgentHealthInGrid(agent.id);
    });

    grid.appendChild(card);
  }
}

async function testSingleAgentHealthInGrid(agentId) {
  const dot = $(`dot-${agentId}`);
  const txt = $(`txt-${agentId}`);
  const tokens = $(`tokens-${agentId}`);
  
  if (!dot || !txt) return;

  dot.className = 'lib-status-dot checking';
  txt.textContent = 'Đang kiểm tra...';
  txt.style.color = 'var(--warning)';
  if (tokens) tokens.style.display = 'none';

  try {
    let res;
    if (agentId.startsWith('default-')) {
      const agent = state.defaultAgents.find(a => `default-${a.name.toLowerCase()}` === agentId);
      if (!agent) throw new Error('Không tìm thấy Agent mặc định');
      res = await apiPost('/api/health-check', {
        provider: agent.provider,
        model: agent.model,
        api_key: ''
      });
    } else {
      res = await apiPost(`/api/library/agents/${agentId}/health`, {});
    }

    if (res.ok) {
      dot.className = 'lib-status-dot ok';
      txt.textContent = `Sẵn sàng (${res.latency_ms}ms)`;
      txt.style.color = 'var(--success)';
      
      if (res.token_info && tokens) {
        tokens.textContent = `${res.token_info.total_tokens} tokens`;
        tokens.style.display = 'inline';
      }
    } else {
      dot.className = 'lib-status-dot error';
      txt.textContent = `Lỗi: ${res.error}`;
      txt.style.color = 'var(--danger)';
    }
  } catch (e) {
    dot.className = 'lib-status-dot error';
    txt.textContent = `Lỗi kết nối: ${e.message}`;
    txt.style.color = 'var(--danger)';
  }
}

async function loadSkills() {
  if (state.skills.length > 0) {
    renderLibrarySkills();
    return;
  }
  const grid = $('lib-skill-grid');
  grid.innerHTML = '<div class="lib-empty-state">Đang tải bộ skill...</div>';
  try {
    const data = await apiGet('/api/library/skills');
    state.skills = data.skills || [];
    renderLibrarySkills();
  } catch (e) {
    grid.innerHTML = `<div class="lib-empty-state">❌ Không thể tải bộ skill: ${e.message}</div>`;
  }
}

function renderLibrarySkills() {
  const grid = $('lib-skill-grid');
  grid.innerHTML = '';
  
  for (const skill of state.skills) {
    const card = document.createElement('div');
    card.className = 'lib-skill-card';
    card.innerHTML = `
      <div class="lib-skill-name">${escHtml(skill.name)}</div>
      <div class="lib-skill-desc">${escHtml(skill.description)}</div>
    `;
    card.addEventListener('click', () => {
      openLibAgentModal({
        name: skill.name.replace(/^[^\s]+\s+/, ''), // Strip emoji
        avatar_emoji: skill.name.match(/^[^\s]+/)?.[0] || '🤖',
        system_prompt: skill.system_prompt,
        provider: 'gemini',
        model: 'gemini-2.0-flash',
        description: skill.description,
      });
    });
    grid.appendChild(card);
  }
}

function openLibAgentModal(agent = null) {
  state.editingLibAgentId = agent ? (agent.id || null) : null;
  
  if (agent && agent.is_default) {
    $('lib-agent-modal-title').textContent = agent.is_customized ? 'Chỉnh sửa Agent mặc định (Đã sửa)' : 'Chỉnh sửa Agent mặc định';
  } else if (agent) {
    $('lib-agent-modal-title').textContent = 'Chỉnh sửa Agent';
  } else {
    $('lib-agent-modal-title').textContent = 'Tạo Agent mới';
  }
  
  $('lib-agent-name').value = agent ? (agent.name || '') : '';
  $('lib-agent-emoji').value = agent ? (agent.avatar_emoji || '') : '';
  $('lib-agent-desc').value = agent ? (agent.description || '') : '';
  $('lib-agent-provider').value = agent ? (agent.provider || 'gemini') : 'gemini';
  $('lib-agent-apikey').value = agent ? (agent.api_key || '') : '';
  $('lib-agent-system').value = agent ? (agent.system_prompt || '') : '';
  
  const resultStrip = $('lib-health-result');
  resultStrip.style.display = 'none';
  resultStrip.className = 'health-result';
  resultStrip.innerHTML = '';

  const inputEl = $('lib-agent-model-input');
  if (inputEl) inputEl.value = '';

  updateLibAgentModelsDropdown().then(() => {
    if (agent) {
      if (agent.provider === 'litert_lm') {
        if (inputEl) inputEl.value = agent.model || '';
      } else {
        $('lib-agent-model').value = agent.model || '';
      }
    }
  });

  $('modal-lib-agent').style.display = 'flex';
  setTimeout(() => $('lib-agent-name').focus(), 100);
}

function closeLibAgentModal() {
  $('modal-lib-agent').style.display = 'none';
}

async function updateLibAgentModelsDropdown() {
  const provider = $('lib-agent-provider').value;
  const def = PROVIDER_DEFAULTS[provider] || {};

  if (!$('lib-agent-emoji').value) {
    $('lib-agent-emoji').placeholder = def.emoji || '🤖';
  }

  const inputEl = $('lib-agent-model-input');
  const selectEl = $('lib-agent-model');
  
  if (provider === 'litert_lm') {
    selectEl.style.display = 'none';
    if (inputEl) inputEl.style.display = 'block';
    return;
  } else {
    selectEl.style.display = 'block';
    if (inputEl) inputEl.style.display = 'none';
  }

  selectEl.innerHTML = '<option value="">Đang tải danh sách models...</option>';
  selectEl.disabled = true;

  try {
    const models = await apiGet(`/api/models/${provider}`);
    selectEl.innerHTML = '';
    
    if (provider === 'openrouter') {
      const freeModels = models.filter(m => m.endsWith(':free'));
      const paidModels = models.filter(m => !m.endsWith(':free'));
      
      if (freeModels.length > 0) {
        const groupFree = document.createElement('optgroup');
        groupFree.label = '🆓 Miễn phí (Free)';
        for (const model of freeModels) {
          const opt = document.createElement('option');
          opt.value = model;
          opt.textContent = model;
          if (model === def.model) opt.selected = true;
          groupFree.appendChild(opt);
        }
        selectEl.appendChild(groupFree);
      }
      
      if (paidModels.length > 0) {
        const groupPaid = document.createElement('optgroup');
        groupPaid.label = '💰 Trả phí (Paid)';
        for (const model of paidModels) {
          const opt = document.createElement('option');
          opt.value = model;
          opt.textContent = model;
          if (model === def.model) opt.selected = true;
          groupPaid.appendChild(opt);
        }
        selectEl.appendChild(groupPaid);
      }
    } else if (provider === 'gemini' && models.length > 5) {
      // Group Gemini models by generation
      const groups = {
        '🚀 Gemini 3.x': [],
        '⚡ Gemini 2.5': [],
        '💎 Gemini 2.0': [],
        '🔷 Gemini 1.x': [],
        '🧩 Gemma': [],
        '🔹 Khác': [],
      };
      for (const model of models) {
        if (model.startsWith('gemma-')) groups['🧩 Gemma'].push(model);
        else if (/^gemini-3/.test(model)) groups['🚀 Gemini 3.x'].push(model);
        else if (/^gemini-2\.5/.test(model)) groups['⚡ Gemini 2.5'].push(model);
        else if (/^gemini-2\.0/.test(model)) groups['💎 Gemini 2.0'].push(model);
        else if (/^gemini-1/.test(model)) groups['🔷 Gemini 1.x'].push(model);
        else groups['🔹 Khác'].push(model);
      }
      for (const [label, list] of Object.entries(groups)) {
        if (list.length === 0) continue;
        const grp = document.createElement('optgroup');
        grp.label = label;
        for (const model of list) {
          const opt = document.createElement('option');
          opt.value = model;
          opt.textContent = model;
          if (model === def.model) opt.selected = true;
          grp.appendChild(opt);
        }
        selectEl.appendChild(grp);
      }
    } else {
      for (const model of models) {
        const opt = document.createElement('option');
        opt.value = model;
        opt.textContent = model;
        if (model === def.model) {
          opt.selected = true;
        }
        selectEl.appendChild(opt);
      }
    }
  } catch (e) {
    console.warn(`Failed to fetch models for ${provider}:`, e);
    selectEl.innerHTML = `<option value="${def.model || ''}" selected>${def.model || ''} (mặc định)</option>`;
  } finally {
    selectEl.disabled = false;
  }
}

async function saveLibAgent() {
  const name = $('lib-agent-name').value.trim();
  if (!name) { $('lib-agent-name').focus(); return; }

  const provider = $('lib-agent-provider').value;
  const def = PROVIDER_DEFAULTS[provider] || {};
  
  const model = provider === 'litert_lm'
    ? ($('lib-agent-model-input') ? $('lib-agent-model-input').value.trim() : '')
    : $('lib-agent-model').value || def.model || '';

  const payload = {
    id: state.editingLibAgentId || '',
    name,
    provider,
    model,
    avatar_emoji: $('lib-agent-emoji').value.trim() || def.emoji || '🤖',
    description: $('lib-agent-desc').value.trim(),
    api_key: $('lib-agent-apikey').value.trim(),
    system_prompt: $('lib-agent-system').value.trim(),
  };

  try {
    await apiPost('/api/library/agents', payload);
    showToast('✅ Đã lưu Agent vào Kho thành công!');
    closeLibAgentModal();
    await loadLibraryAgents();
  } catch (e) {
    alert('Lỗi lưu Agent: ' + e.message);
  }
}

async function duplicateLibAgent(agentId) {
  if (agentId.startsWith('default-')) {
    const isCustomized = state.libraryAgents.some(a => a.id === agentId);
    let agent;
    if (isCustomized) {
      agent = state.libraryAgents.find(a => a.id === agentId);
    } else {
      agent = state.defaultAgents.find(a => `default-${a.name.toLowerCase()}` === agentId);
    }
    if (!agent) return;
    const payload = {
      name: agent.name + ' (copy)',
      provider: agent.provider,
      model: agent.model,
      avatar_emoji: agent.avatar_emoji,
      description: `Bản sao của agent mặc định ${agent.name}.`,
      system_prompt: agent.system_prompt || '',
      api_key: agent.api_key || '',
    };
    try {
      await apiPost('/api/library/agents', payload);
      showToast('✅ Đã nhân bản Agent mặc định thành công!');
      await loadLibraryAgents();
    } catch (e) {
      showToast(`❌ Lỗi: ${e.message}`, 'error');
    }
    return;
  }

  try {
    await apiPost(`/api/library/agents/${agentId}/duplicate`, {});
    showToast('✅ Đã nhân bản Agent!');
    await loadLibraryAgents();
  } catch (e) {
    showToast(`❌ Lỗi nhân bản: ${e.message}`, 'error');
  }
}

async function deleteLibAgent(agentId, name) {
  const isDefault = agentId.startsWith('default-');
  const msg = isDefault 
    ? `Bạn có chắc muốn khôi phục Agent mặc định "${name}" về cấu hình ban đầu?`
    : `Bạn có chắc muốn xóa Agent "${name}" khỏi kho?`;

  if (!confirm(msg)) return;
  try {
    await apiDelete(`/api/library/agents/${agentId}`);
    showToast(isDefault ? '🔄 Đã khôi phục cấu hình mặc định.' : '🗑 Đã xóa Agent khỏi kho.');
    await loadLibraryAgents();
  } catch (e) {
    showToast(`❌ Lỗi: ${e.message}`, 'error');
  }
}

async function addLibraryAgentToRoom(agent) {
  const isRoomModalOpen = els.modalRoom.style.display !== 'none';
  
  const newAgentConfig = {
    name: agent.name,
    provider: agent.provider,
    model: agent.model,
    avatar_emoji: agent.avatar_emoji,
    system_prompt: agent.system_prompt || '',
    api_key: agent.api_key || '',
  };

  if (isRoomModalOpen) {
    state.tempAgents.push(newAgentConfig);
    renderAgentEditor();
    showToast(`✅ Đã thêm ${agent.avatar_emoji} ${agent.name} vào cấu hình phòng!`);
  } else if (state.currentRoomId) {
    const room = state.rooms.find(r => r.room_id === state.currentRoomId);
    if (!room) return;
    
    const updatedAgents = [...room.agents.map(a => ({
      name: a.name, provider: a.provider, model: a.model,
      avatar_emoji: a.avatar_emoji, system_prompt: a.system_prompt || '', api_key: a.api_key || ''
    })), newAgentConfig];

    try {
      await apiPut(`/api/rooms/${state.currentRoomId}`, {
        name: room.name,
        agents: updatedAgents
      });
      showToast(`✅ Đã thêm ${agent.avatar_emoji} ${agent.name} trực tiếp vào phòng chat!`);
    } catch (e) {
      showToast(`❌ Lỗi: ${e.message}`, 'error');
    }
  } else {
    showToast('⚠️ Vui lòng mở hoặc chọn một phòng chat trước!', 'error');
  }
}

async function testLibAgentHealth() {
  const resultStrip = $('lib-health-result');
  resultStrip.style.display = 'block';
  resultStrip.className = 'health-result checking';
  resultStrip.innerHTML = '⚡ Đang chạy health check...';

  const provider = $('lib-agent-provider').value;
  const model = provider === 'litert_lm'
    ? ($('lib-agent-model-input') ? $('lib-agent-model-input').value.trim() : '')
    : $('lib-agent-model').value;
  const api_key = $('lib-agent-apikey').value.trim();

  try {
    const res = await apiPost('/api/health-check', {
      provider,
      model,
      api_key
    });

    if (res.ok) {
      resultStrip.className = 'health-result ok';
      let html = `<strong>✅ Thành công!</strong> Kết nối ổn định.<br/>`;
      html += `Độ trễ: ${res.latency_ms} ms.`;
      if (res.token_info) {
        html += `<br/>Tokens sử dụng: ${res.token_info.prompt_tokens} (input) / ${res.token_info.completion_tokens} (output).`;
      }
      resultStrip.innerHTML = html;
    } else {
      resultStrip.className = 'health-result error';
      resultStrip.innerHTML = `<strong>❌ Lỗi kết nối:</strong> ${escHtml(res.error)}`;
    }
  } catch (e) {
    resultStrip.className = 'health-result error';
    resultStrip.innerHTML = `<strong>❌ Lỗi kết nối:</strong> ${escHtml(e.message)}`;
  }
}

function openSkillPicker() {
  const picker = $('modal-skill-picker');
  const list = $('picker-skill-list');
  list.innerHTML = '';
  
  if (state.skills.length === 0) {
    list.innerHTML = '<div style="padding:10px;text-align:center;color:var(--text-muted)">Không có skill nào sẵn có.</div>';
    picker.style.display = 'flex';
    return;
  }

  for (const skill of state.skills) {
    const item = document.createElement('div');
    item.className = 'picker-skill-item';
    item.innerHTML = `
      <div>
        <div class="picker-skill-name">${escHtml(skill.name)}</div>
        <div class="picker-skill-desc">${escHtml(skill.description)}</div>
      </div>
    `;
    item.addEventListener('click', () => {
      $('lib-agent-system').value = skill.system_prompt;
      const event = new Event('input', { bubbles: true });
      $('lib-agent-system').dispatchEvent(event);
      closeSkillPicker();
    });
    list.appendChild(item);
  }
  picker.style.display = 'flex';
}

function closeSkillPicker() {
  $('modal-skill-picker').style.display = 'none';
}

// ── Init ───────────────────────────────────────────────────────

async function init() {
  await loadDefaultAgents();
  await loadRooms();
  await refreshSettingsStatus();
  bindEvents();
  autoResizeTextarea();
}

// ── Event Bindings ─────────────────────────────────────────────
function bindEvents() {
  els.sendBtn.addEventListener('click', sendMessage);

  els.messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  els.messageInput.addEventListener('input', () => {
    autoResizeTextarea();
    updateSendBtn();
    checkMentions(els.messageInput.value);
  });

  $('btn-new-room').addEventListener('click', openCreateRoomModal);
  $('btn-create-first-room').addEventListener('click', openCreateRoomModal);

  $('btn-close-room-modal').addEventListener('click', closeRoomModal);
  $('btn-cancel-room').addEventListener('click', closeRoomModal);
  $('btn-save-room').addEventListener('click', saveRoom);
  $('btn-add-agent').addEventListener('click', openAddAgentModal);

  $('btn-close-agent-modal').addEventListener('click', closeAgentModal);
  $('btn-cancel-agent').addEventListener('click', closeAgentModal);
  $('btn-save-agent').addEventListener('click', saveAgent);

  els.agentProviderSelect.addEventListener('change', updateAgentModelsDropdown);
  els.agentSkillSelect?.addEventListener('change', (e) => {
    const skillName = e.target.value;
    if (skillName) {
      const skill = state.skills.find(s => s.name === skillName);
      if (skill) {
        els.agentSystemInput.value = skill.system_prompt;
      }
    }
  });

  $('btn-room-settings').addEventListener('click', () => {
    if (!state.currentRoomId) return;
    const room = state.rooms.find(r => r.room_id === state.currentRoomId);
    if (!room) return;
    state.isEditingRoom = true;
    state.editingAgentIndex = null;
    state.tempAgents = JSON.parse(JSON.stringify(room.agents.map(a => ({
      name: a.name, provider: a.provider, model: a.model,
      avatar_emoji: a.avatar_emoji, system_prompt: a.system_prompt || '', api_key: '',
    }))));
    els.roomNameInput.value = room.name;
    els.modalRoomTitle.textContent = 'Cấu hình phòng';
    $('btn-save-room').textContent = 'Lưu thay đổi';
    $('btn-save-room').onclick = null;
    renderAgentEditor();
    els.modalRoom.style.display = 'flex';
  });

  // Delete room
  $('btn-delete-room').addEventListener('click', deleteCurrentRoom);

  // Mobile sidebar toggle
  $('btn-toggle-sidebar').addEventListener('click', () => {
    document.querySelector('.sidebar').classList.toggle('open');
  });

  // ── Settings modal ───────────────────────────────────────────
  $('btn-settings').addEventListener('click', openSettings);
  $('btn-close-settings').addEventListener('click', closeSettings);
  $('btn-close-settings-footer').addEventListener('click', closeSettings);
  $('modal-settings').addEventListener('click', (e) => {
    if (e.target === $('modal-settings')) closeSettings();
  });



  // API Key save/clear buttons
  $('btn-save-gemini-key').addEventListener('click', () => saveApiKey('gemini', 'gemini-api-key-input'));
  $('btn-clear-gemini-key').addEventListener('click', () => clearApiKey('gemini', 'gemini-api-key-input'));
  $('btn-save-openai-key').addEventListener('click', () => saveApiKey('openai', 'openai-api-key-input'));
  $('btn-clear-openai-key').addEventListener('click', () => clearApiKey('openai', 'openai-api-key-input'));
  $('btn-save-anthropic-key').addEventListener('click', () => saveApiKey('anthropic', 'anthropic-api-key-input'));
  $('btn-clear-anthropic-key').addEventListener('click', () => clearApiKey('anthropic', 'anthropic-api-key-input'));
  
  $('btn-save-openrouter-key').addEventListener('click', () => saveApiKey('openrouter', 'openrouter-api-key-input'));
  $('btn-clear-openrouter-key').addEventListener('click', () => clearApiKey('openrouter', 'openrouter-api-key-input'));
  $('btn-save-freemodel-key').addEventListener('click', () => saveApiKey('freemodel', 'freemodel-api-key-input'));
  $('btn-clear-freemodel-key').addEventListener('click', () => clearApiKey('freemodel', 'freemodel-api-key-input'));
  
  $('btn-save-freemodel-url').addEventListener('click', async () => {
    const url = $('freemodel-base-url-input').value.trim();
    try {
      await apiPost('/api/settings/base-url', { provider: 'freemodel', base_url: url });
      showToast('✅ Freemodel Base URL đã lưu!');
      $('freemodel-base-url-input').value = '';
      await refreshSettingsStatus();
    } catch (e) {
      showToast(`❌ Lỗi: ${e.message}`, 'error');
    }
  });



  // Close modal on overlay click

  $('modal-room').addEventListener('click', (e) => {
    if (e.target === els.modalRoom) closeRoomModal();
  });
  $('modal-agent').addEventListener('click', (e) => {
    if (e.target === els.modalAgent) closeAgentModal();
  });

  // Agent Library Event Bindings
  $('btn-agent-library').addEventListener('click', openLibrary);
  $('btn-close-library').addEventListener('click', closeLibrary);
  $('btn-lib-new-agent').addEventListener('click', () => openLibAgentModal(null));
  $('btn-close-lib-agent').addEventListener('click', closeLibAgentModal);
  $('btn-cancel-lib-agent').addEventListener('click', closeLibAgentModal);
  $('btn-save-lib-agent').addEventListener('click', saveLibAgent);
  $('btn-test-lib-agent').addEventListener('click', testLibAgentHealth);
  $('lib-agent-provider').addEventListener('change', updateLibAgentModelsDropdown);
  $('lib-search').addEventListener('input', renderLibraryAgents);

  document.querySelectorAll('.library-panel-tabs .lib-tab').forEach(tabBtn => {
    tabBtn.addEventListener('click', () => {
      showLibraryTab(tabBtn.dataset.tab);
    });
  });

  $('btn-pick-skill').addEventListener('click', openSkillPicker);
  $('btn-close-skill-picker').addEventListener('click', closeSkillPicker);

  // Library panel overlay click to close
  $('library-panel-overlay').addEventListener('click', closeLibrary);

  // New toolbar button to open library
  $('btn-library-panel').addEventListener('click', openLibrary);
  $('modal-lib-agent').addEventListener('click', (e) => {
    if (e.target === $('modal-lib-agent')) closeLibAgentModal();
  });
  $('modal-skill-picker').addEventListener('click', (e) => {
    if (e.target === $('modal-skill-picker')) closeSkillPicker();
  });

  // Keyboard shortcut: Escape closes modals and panel
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      if (els.modalAgent.style.display !== 'none') closeAgentModal();
      else if (els.modalRoom.style.display !== 'none') closeRoomModal();
      else if ($('modal-settings').style.display !== 'none') closeSettings();
      else if ($('library-panel').classList.contains('open')) closeLibrary();
      else if ($('modal-lib-agent').style.display !== 'none') closeLibAgentModal();
      else if ($('modal-skill-picker').style.display !== 'none') closeSkillPicker();
    }
  });


  // Ping to keep WS alive
  setInterval(() => {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, 25000);
}

// ── Start ──────────────────────────────────────────────────────
init().catch(console.error);
