#!/bin/bash
# ── Start AI Agent Chat ──────────────────────────────────────────
# Activates venv and starts the backend server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
BACKEND_DIR="$SCRIPT_DIR/backend"

# Check .env exists
if [ ! -f "$SCRIPT_DIR/.env" ]; then
  echo "⚠️  .env không tồn tại. Copy từ .env.example..."
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  echo "➡️  Vui lòng điền API keys vào file .env rồi chạy lại script này."
  echo "   $SCRIPT_DIR/.env"
  exit 1
fi

# Create venv if not exists
NEED_INSTALL=false
if [ ! -d "$VENV_DIR" ]; then
  echo "📦 Tạo virtual environment..."
  python3 -m venv "$VENV_DIR"
  NEED_INSTALL=true
fi

# Activate & install
source "$VENV_DIR/bin/activate"

if [ "$NEED_INSTALL" = true ]; then
  echo "📦 Cài đặt dependencies (giới hạn kết nối 15s)..."
  pip install -r "$BACKEND_DIR/requirements.txt" -q --timeout 15 --disable-pip-version-check
fi

echo ""
echo "🚀 Khởi động AI Agent Chat tại http://localhost:8000"
echo "   Nhấn Ctrl+C để dừng"
echo ""

cd "$BACKEND_DIR" && uvicorn main:app --reload --port 8000 --host 0.0.0.0
