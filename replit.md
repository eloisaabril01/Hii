# DeepSeek AI REST API

A Flask-based REST API that wraps the DeepSeek AI chat interface.

## Stack
- **Language:** Python 3.11
- **Framework:** Flask
- **Dependencies:** flask, pycryptodome, requests, rich

## Running
The app runs on port 5000 via the "Start application" workflow (`python main.py`).

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info and endpoint listing |
| GET | `/models` | List all 18 available DeepSeek models |
| POST | `/init` | Initialize a chat session |
| POST | `/chat` | Send a message and get a response |
| DELETE | `/session/<session_id>` | End a chat session |

## Usage Flow

1. **List models** — `GET /models`
2. **Init session** — `POST /init` with `{"model": "DeepSeek-V3"}`
3. **Chat** — `POST /chat` with `{"session_id": "...", "message": "Hello!"}`
4. **End session** — `DELETE /session/<session_id>`
