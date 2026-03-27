from fastapi import WebSocket
from fastapi.websockets import WebSocketState
import json

class ConnectionManager:
    def __init__(self):
        # One active socket per user_id (latest connection wins)
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        # If there's already a stale connection, clean it up silently
        old = self.active_connections.get(user_id)
        if old and old is not websocket:
            try:
                await old.close()
            except Exception:
                pass
        self.active_connections[user_id] = websocket
        print(f"[WS] User {user_id} connected. Active: {list(self.active_connections.keys())}")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            print(f"[WS] User {user_id} disconnected.")

    async def send_personal_message(self, message: dict, user_id: str):
        websocket = self.active_connections.get(user_id)
        if not websocket:
            print(f"[WS] No active connection for user {user_id} — message dropped.")
            return

        # Check the connection is still open before sending
        if websocket.client_state != WebSocketState.CONNECTED:
            print(f"[WS] Stale socket for user {user_id} — cleaning up.")
            self.disconnect(user_id)
            return

        try:
            await websocket.send_text(json.dumps(message))
            print(f"[WS] Sent '{message.get('type')}' to user {user_id}")
        except Exception as e:
            print(f"[WS] Send failed for user {user_id}: {e}")
            self.disconnect(user_id)

notifier = ConnectionManager()

