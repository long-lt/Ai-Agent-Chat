# Library Slide-Over Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-screen Agent Library modal with a slide-over panel for faster agent addition to chat rooms.

**Architecture:** Three files change: `index.html` (panel HTML + toolbar button), `styles.css` (panel + compact card styles), `app.js` (open/close logic + compact card rendering). Backend unchanged.

**Tech Stack:** Vanilla JS, CSS3, HTML5

---

### Task 1: Update index.html — Panel structure + toolbar button

**Files:** Modify `frontend/index.html`

- [ ] **Step 1: Replace the modal-library HTML block with slide-over panel**

Replace the entire `#modal-library` div block (lines 432-470) with:

```html
  <!-- ── Library Slide-Over Panel ─────────────────────────── -->
  <div class="library-panel-overlay" id="library-panel-overlay" style="display:none"></div>
  <div class="library-panel" id="library-panel">
    <div class="library-panel-header">
      <h3>🗂 Kho Agent</h3>
      <button class="icon-btn" id="btn-close-library">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="library-panel-tabs">
      <button class="lib-tab active" data-tab="agents">Agents của tôi</button>
      <button class="lib-tab" data-tab="skills">Bộ Skill</button>
    </div>
    <div class="lib-panel" id="lib-panel-agents">
      <div class="lib-toolbar">
        <input type="text" class="lib-search" id="lib-search" placeholder="🔍 Tìm agent..." />
        <button class="btn-primary" id="btn-lib-new-agent">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          Tạo Agent
        </button>
      </div>
      <div class="lib-agent-grid" id="lib-agent-grid">
        <!-- Agent cards injected by JS -->
      </div>
    </div>
    <div class="lib-panel" id="lib-panel-skills" style="display:none">
      <p class="lib-skills-hint">Chọn một skill để áp dụng system prompt khi tạo agent mới</p>
      <div class="lib-skill-grid" id="lib-skill-grid">
        <!-- Skill cards injected by JS -->
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Add toolbar button in chat header**

In the `#chat-header-right` div (line 73), add a new button **before** `#btn-room-settings`:

```html
<div class="chat-header-right">
  <button class="icon-btn" id="btn-library-panel" title="Kho Agent">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
  </button>
  <button class="icon-btn" id="btn-room-settings" title="Cài đặt phòng">
    ...
```

---

### Task 2: Add CSS for slide-over panel and compact cards

**Files:** Modify `frontend/styles.css`

- [ ] **Step 1: Add panel + overlay CSS before `.library-tabs` block**

Add after the `.modal` block (after line 759) or before `.modal-library` (line 1338):

```css
/* ── Library Slide-Over Panel ────────────────────────────── */
.library-panel-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  z-index: 999;
  animation: fadeIn 0.2s ease;
}

.library-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 380px;
  max-width: 90vw;
  height: 100vh;
  background: var(--bg-2);
  border-left: 1px solid var(--glass-border);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  box-shadow: -8px 0 32px rgba(0, 0, 0, 0.4);
  transform: translateX(100%);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.library-panel.open {
  transform: translateX(0);
}

.library-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.library-panel-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.library-panel-tabs {
  display: flex;
  gap: 4px;
  padding: 12px 20px 0;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.library-panel .lib-panel {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 20px;
}

.library-panel .lib-panel::-webkit-scrollbar { width: 6px; }
.library-panel .lib-panel::-webkit-scrollbar-thumb { background: var(--bg-3); border-radius: 3px; }

.library-panel .lib-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.library-panel .lib-search {
  flex: 1;
  padding: 7px 12px;
  background: var(--bg-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-family: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color var(--transition);
}

.library-panel .lib-search:focus { border-color: var(--accent); }
.library-panel .lib-search::placeholder { color: var(--text-muted); }

.library-panel .btn-primary {
  padding: 7px 14px;
  font-size: 13px;
  white-space: nowrap;
}
```

- [ ] **Step 2: Replace existing modal-library styles with compact card styles**

Replace the `.modal-library` block (lines 1338-1343) and the `.lib-agent-card` through `.lib-agent-actions` styles (lines 1419-1556):

```css
/* ── Compact Agent Cards ──────────────────────────────────── */
.lib-agent-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.lib-agent-card {
  background: var(--bg-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  transition: border-color var(--transition), box-shadow var(--transition);
}

.lib-agent-card:hover {
  border-color: rgba(255,255,255,0.12);
  box-shadow: 0 2px 12px rgba(0,0,0,0.2);
}

.lib-agent-card-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lib-agent-card .lib-agent-avatar {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  flex-shrink: 0;
  border: 2px solid transparent;
}

.lib-agent-card .lib-agent-info {
  flex: 1;
  min-width: 0;
}

.lib-agent-card .lib-agent-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lib-agent-card .lib-agent-name .default-badge {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  margin-left: 4px;
  font-weight: 400;
}

.lib-agent-card .lib-agent-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.lib-agent-provider-badge {
  padding: 1px 6px;
  border-radius: 100px;
  background: var(--bg-3);
  border: 1px solid var(--glass-border);
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.lib-agent-desc {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
  margin-top: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  padding-left: 44px;
}

.lib-agent-card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  padding-left: 44px;
}

.lib-agent-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  cursor: pointer;
}

.lib-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.lib-status-dot.ok { background: var(--success); box-shadow: 0 0 5px var(--success); }
.lib-status-dot.error { background: var(--danger); }
.lib-status-dot.ratelimit { background: var(--warning); }
.lib-status-dot.idle { background: var(--text-muted); }
.lib-status-dot.checking { background: var(--warning); animation: pulse 1s ease infinite; }

.lib-token-info {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: auto;
}

.lib-agent-actions {
  display: flex;
  gap: 4px;
}

.lib-btn {
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--text-muted);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: background var(--transition), color var(--transition);
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}

.lib-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.lib-btn.lib-btn-danger:hover { color: var(--danger); }
```

- [ ] **Step 3: Update "Add to Room" button — always visible**

Replace the `.lib-add-to-room-btn` block (lines 1708-1731):

```css
.lib-add-to-room-btn {
  padding: 5px 12px;
  border-radius: 100px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(108,111,255,0.15);
  border: 1px solid rgba(108,111,255,0.3);
  color: var(--accent);
  cursor: pointer;
  white-space: nowrap;
  transition: background var(--transition), color var(--transition);
  flex-shrink: 0;
}

.lib-add-to-room-btn:hover {
  background: rgba(108,111,255,0.3);
  color: #fff;
}
```

- [ ] **Step 4: Remove old modal CSS blocks**

Delete these unused CSS blocks:
- `.modal-library` (lines 1338-1343)
- `.library-tabs` (lines 1350-1356)
- The old `.lib-agent-grid`, `.lib-agent-card`, `.lib-agent-card-top`, `.lib-agent-avatar`, `.lib-agent-info`, `.lib-agent-name`, `.lib-agent-meta`, `.lib-agent-provider-badge`, `.lib-agent-desc`, `.lib-agent-status`, `.lib-status-dot`, `.lib-token-info`, `.lib-agent-actions`, `.lib-btn` blocks (lines 1413-1556) — replaced by compact card styles above.

- [ ] **Step 5: Remove `.lib-add-to-room-btn` overlay + hover rule**

Delete the old `.lib-add-to-room-btn` and `.lib-agent-card:hover .lib-add-to-room-btn` rules (lines 1708-1731) — replaced by Step 3.

---

### Task 3: Update JavaScript — panel logic + compact card rendering

**Files:** Modify `frontend/app.js`

- [ ] **Step 1: Rewrite `openLibrary` and `closeLibrary` functions**

Replace lines 1250-1258:

```javascript
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
```

- [ ] **Step 2: Update `showLibraryTab` to target new panel tab class**

Replace lines 1261-1274. The tabs now use `.library-panel-tabs` instead of `.library-tabs`:

```javascript
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
```

- [ ] **Step 3: Rewrite `renderLibraryAgents` for compact cards**

Replace the card HTML inside `renderLibraryAgents()` (the `card.innerHTML` block starting around line 1345). The compact card should have:

```javascript
card.innerHTML = `
  <div class="lib-agent-card-row">
    <div class="lib-agent-avatar" style="background: ${hexToRgba(color, 0.15)}; border-color: ${color}; color: ${color}">
      ${agent.avatar_emoji || '🤖'}
    </div>
    <div class="lib-agent-info">
      <div class="lib-agent-name">
        ${escHtml(agent.name)}
        ${agent.is_default ? `<span class="default-badge" style="background:${agent.is_customized ? 'rgba(108,111,255,0.15)' : 'rgba(255,255,255,0.08)'};color:${agent.is_customized ? 'var(--accent)' : 'var(--text-muted)'}">${agent.is_customized ? 'Đã sửa' : 'Mặc định'}</span>` : ''}
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
        ${agent.is_customized ? `<button class="lib-btn lib-btn-danger lib-restore-btn" data-id="${agent.id}">🔄</button>` : ''}
      ` : `
        <button class="lib-btn lib-edit-btn" data-id="${agent.id}">✏️</button>
        <button class="lib-btn lib-duplicate-btn" data-id="${agent.id}">📋</button>
        <button class="lib-btn lib-btn-danger lib-delete-btn" data-id="${agent.id}">🗑</button>
      `}
    </div>
  </div>
`;
```

- [ ] **Step 4: Add event listeners for panel, overlay, and escape key**

Add after the existing `$('btn-agent-library').addEventListener('click', openLibrary)` (around line 1973):

```javascript
// Library panel overlay click to close
$('library-panel-overlay').addEventListener('click', closeLibrary);

// New toolbar button to open library
$('btn-library-panel').addEventListener('click', openLibrary);

// Escape key closes panel
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && $('library-panel').classList.contains('open')) {
    closeLibrary();
  }
});
```

Also change the modal-library overlay click handler (around line 1992-1993). The old code:
```javascript
$('modal-library').addEventListener('click', (e) => {
  if (e.target === $('modal-library')) closeLibrary();
});
```
This should be removed since the overlay is now `#library-panel-overlay` (handled above).

- [ ] **Step 5: Update `$('modal-library')` element references in event listeners**

Find and update these references (they should already point to the new `#library-panel` or `#btn-close-library` etc. since only the HTML IDs changed):

The existing event listeners use these IDs which stay the same:
- `$('btn-close-library')` → still works
- `$('btn-agent-library')` → still works  
- `$('lib-search')` → still works
- `$('btn-lib-new-agent')` → still works

But the old `$('modal-library').addEventListener('click', ...)` on line 1992 needs to be removed (handled in Step 4).

Also check: on line 2008, there is `else if ($('modal-library').style.display !== 'none') closeLibrary();` — this should be updated to check the panel class instead:

```javascript
else if ($('library-panel').classList.contains('open')) closeLibrary();
```

---

### Task 4: Verify changes work

- [ ] **Step 1: Run frontend checks**

No build step for vanilla JS. Open `index.html` in browser or serve via the backend:

```bash
cd backend && python main.py
```

Verify:
- Sidebar "Kho Agent" button opens slide-over panel from right
- Chat header folder icon button also opens panel
- Panel slides in smoothly
- Overlay is visible behind panel, chat dimmed but visible
- Clicking overlay closes panel
- Escape key closes panel
- Compact agent cards show with always-visible "[+] Thêm" button
- Adding agent from panel shows toast and keeps panel open
- Switching to Skills tab works
- Creating/editing/deleting agents from panel works
