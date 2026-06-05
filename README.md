# AI Agent Group Chat 🤖💬

Web chat nhóm giống ChatGPT với sự tham gia của một đội ngũ nhiều AI Agent (Bot) cùng trò chuyện. Mỗi agent có thể đóng một vai trò khác nhau và sử dụng các provider khác nhau (Gemini, OpenAI, Anthropic, OpenRouter, FreeModel).

## 🌟 Tính năng nổi bật

- 🤖 **Multi-Agent Collaboration**: Nhiều AI Agent cùng ở trong một phòng chat để giải quyết vấn đề.
- 🔄 **Auto-Fallback & Eviction**: Khi một model trả phí (như OpenRouter) hết tiền hoặc lỗi, hệ thống tự động fallback tìm kiếm các model miễn phí khác (`:free`) thay thế mà không làm gián đoạn cuộc trò chuyện.
- ⚡ **Collaborative Response**: Các Agent nhận thức được câu trả lời của nhau. Agent trả lời sau có thể bổ sung hoặc phản bác ý kiến của Agent trả lời trước.
- 📚 **Kho Agent (Agent Library)**: Lưu trữ các Agent yêu thích thành mẫu (Template) dùng chung cho mọi phòng chat.
- @**Mention**: Gõ `@TênAgent` để chỉ định đích danh một agent cụ thể.
- 🌊 **Real-time Streaming**: Trả lời mượt mà từng từ (token-by-token) qua WebSocket.
- 💾 **Lưu trữ cục bộ**: Tự động lưu lịch sử chat qua SQLite và JSON File.
- 🎨 **Glassmorphism Premium UI**: Giao diện siêu đẹp, dark mode hiện đại, mượt mà.

## 🚀 Cài đặt & Chạy dự án

### 1. Cài đặt Python Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường

Sao chép file mẫu và điền các API key của bạn:

```bash
cp .env.example .env
```
*(Lưu ý: File `.env` và thư mục `backend/data/` đã được thiết lập `.gitignore` để không bị đẩy nhầm API key lên Github).*

Bạn có thể lấy API keys tại:
- **Gemini**: https://aistudio.google.com/app/api-keys
- **OpenRouter**: https://openrouter.ai/keys
- **FreeModel**: Dịch vụ mô hình miễn phí tích hợp sẵn.
- **OpenAI / Anthropic**: Truy cập trang chủ tương ứng.

### 3. Chạy Server

Sử dụng script chạy nhanh:
```bash
chmod +x start.sh
./start.sh
```

Hoặc chạy thủ công qua Uvicorn:
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Bắt đầu sử dụng
Mở trình duyệt và truy cập: **http://localhost:8000**

## 📂 Cấu trúc mã nguồn

```text
Ai-Agent-Chat/
├── backend/
│   ├── main.py              # Server FastAPI chính
│   ├── chat_room.py         # Quản lý WebSocket & Logic Fallback
│   ├── models_helper.py     # Quản lý danh sách Models
│   ├── database.py          # SQLite
│   ├── agent_library.py     # Kho Agent
│   └── agents/              # Các Module kết nối API (Gemini, OpenRouter,...)
├── frontend/
│   ├── index.html           # UI chính
│   ├── styles.css           # UI Glassmorphism
│   └── app.js               # WebSockets client
├── .gitignore
└── start.sh
```
