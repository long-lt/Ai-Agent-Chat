# Agent Library Slide-Over Panel

## Problem

Adding an agent from Kho Agent (Agent Library) to a chat room requires opening a full-screen modal that hides the chat room. The user must close the modal to see the result, disrupting the chat flow.

## Design

Replace the full-screen `#modal-library` modal with a slide-over panel that slides in from the right side of the screen. The chat room remains visible behind a partial overlay.

### Layout

```
┌──────────────────────────────────────────────────────┐
│  ┌── Sidebar ──┐  ┌── Chat Area ─────────────────┐  │  ┌── Slide Panel (~380px) ─┐
│  │             │  │  [Room Header]  [📂] [⚙️] [🗑] │  │  │  ✕  Kho Agent          │
│  │  Room List  │  │                                │  │  │  [Agents] [Skills]     │
│  │             │  │  ┌── Messages ──────────────┐  │  │  │                        │
│  │             │  │  │  ...                      │  │  │  │  😎 Expert       [+]\  │
│  │             │  │  │  ...                      │  │  │  │  💎 Gemini Pro    [+]\  │
│  │  [Kho] [⚙️] │  │  └──────────────────────────┘  │  │  │  🐍 Python Exp    [+]\  │
│  └────────────┘  │  [Message Input...          ]  │  │  │                        │
│                  └──────────────────────────────────┘  │  │  [➕ Tạo Agent mới]    │
│                                                       │  └────────────────────────┘
└──────────────────────────────────────────────────────┘
```

### Structure

- Panel is a fixed-position div on the right side, `z-index: 1000` (same as modals)
- A semi-transparent overlay covers the rest of the screen (chat area + sidebar)
- Panel has a header close button, tab bar (Agents / Skills), scrollable content area, and footer with create button
- The chat room behind is slightly dimmed but visible

### Compact Agent Cards

Each card in the panel is more compact than the current modal version:

- **Avatar emoji** + **Name** + **Provider badge** in a single row
- **Model name** shown in smaller text below
- **Description** shown in 1-2 lines
- **Health status dot** (small, inline)
- **"[+] Thêm" button** always visible (not hover-revealed), prominent accent color
- **Edit/Duplicate/Delete** as icon-only buttons in the corner (less prominent)

### Trigger

- A new button `📂` (folder icon) is added to `#chat-header-right` in the room toolbar, next to the settings button
- The existing **Kho Agent** button in the sidebar footer continues to work, but now opens the panel instead of the modal
- The existing shortcut in the room creation modal ("Thêm từ Kho Agent") also opens the panel

### Animations

- **Open**: Panel slides in from right (translateX(100%) → translateX(0)) over 250ms ease-out. Overlay fades in simultaneously.
- **Close**: Panel slides out to right over 200ms ease-in. Overlay fades out.
- Smooth cubic-bezier easing consistent with existing modal animations.

### Interaction

- Clicking the overlay closes the panel
- Pressing Escape closes the panel
- Adding an agent via [+] shows a toast but keeps the panel open for further additions
- The panel can be resized/re-positioned via CSS (no drag resize)

## Implementation Plan

### Files to change

1. **`frontend/index.html`**:
   - Replace `#modal-library` block with `<div id="library-panel" class="library-panel">`
   - Add `📂` button to `#chat-header-right`

2. **`frontend/styles.css`**:
   - Add `.library-panel`, `.library-panel.open`, `.library-panel-overlay` styles
   - Add slide animation keyframes
   - Compact card redesign: `.lib-agent-card-compact`
   - Always-visible `.lib-add-to-room-btn` (remove hover-only behavior)

3. **`frontend/app.js`**:
   - Rewrite `openLibrary()`/`closeLibrary()` for panel
   - Rewrite `renderLibraryAgents()` for compact cards
   - Add event listener for new toolbar button
   - Add overlay click + Escape to close

### No backend changes

All API endpoints remain the same. The backend does not need modification.
