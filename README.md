# AI Agent Group Chat

Web chat nhóm giống ChatGPT với nhiều AI Agent cùng tham gia trò chuyện, mỗi agent có thể dùng provider khác nhau (Gemini, OpenAI, Anthropic).

## Tính năng

- 🤖 **Multi-Agent**: Nhiều AI Agent cùng phòng chat (Gemini, GPT, Claude)
- ⚡ **Collaborative Response**: Agent sau xem câu trả lời của agent trước và bổ sung/phản bác
- 🔄 **Agent-to-Agent Debate**: Agents có thể tranh luận với nhau (max 2 vòng)
- @Mention: Gọi agent cụ thể bằng `@TênAgent`
- 🌊 **Streaming**: Response xuất hiện token-by-token
- 💾 **SQLite**: Lịch sử chat được lưu tự động
- 🎨 **Dark Mode UI**: Giao diện glassmorphism premium

## Cài đặt

### 1. Cài Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Tạo file `.env`

```bash
cp ../.env.example ../.env
# Mở .env và điền API keys
```

Lấy API keys tại:
- **Gemini**: https://aistudio.google.com/app/api-keys
- **OpenAI**: https://platform.openai.com/api-keys
- **Anthropic**: https://console.anthropic.com/settings/keys

### 3. Chạy server

```bash
cd backend
python main.py
# hoặc
uvicorn main:app --reload --port 8000
```
or

#### Start by start.sh
```
chmod +x start.sh

./start.sh
```

### 4. Mở trình duyệt

Truy cập: http://localhost:8000

## Cách dùng

1. **Tạo phòng**: Click nút `+` hoặc "Tạo phòng mới"
2. **Thêm Agents**: Chọn provider, model, điền API key (nếu không dùng .env)
3. **Chat**: Gửi tin nhắn → tất cả agents tự động trả lời
4. **@Mention**: Gõ `@Gemini` để chỉ gọi Gemini trả lời

## Cấu trúc

```
Ai-Agent-Chat/
├── backend/
│   ├── main.py           # FastAPI server
│   ├── chat_room.py      # Room & dispatch logic
│   ├── database.py       # SQLite
│   ├── config.py         # Settings
│   └── agents/
│       ├── base_agent.py
│       ├── gemini_agent.py
│       ├── openai_agent.py
│       └── anthropic_agent.py
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
└── .env
```
