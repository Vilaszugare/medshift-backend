from fastapi import WebSocket
from fastapi.websockets import WebSocketState
import json

class ConnectionManager:
    def __init__(self):
        # Multiple connections per user_id (App.jsx global + chat views)
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        active_users = list(self.active_connections.keys())
        conn_count = len(self.active_connections[user_id])
        print(f"[WS] User {user_id} connected (conn #{conn_count}). Active users: {active_users}")

    def disconnect(self, user_id: str, websocket: WebSocket = None):
        if user_id not in self.active_connections:
            return
        if websocket:
            # Remove only the specific websocket
            self.active_connections[user_id] = [
                ws for ws in self.active_connections[user_id] if ws is not websocket
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        else:
            # Remove all connections for this user
            del self.active_connections[user_id]
        print(f"[WS] User {user_id} disconnected. Active users: {list(self.active_connections.keys())}")

    def is_user_online(self, user_id: str) -> bool:
        """Check if a user has at least one active WebSocket connection."""
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    async def send_personal_message(self, message: dict, user_id: str):
        sockets = self.active_connections.get(user_id, [])
        if not sockets:
            print(f"[WS] No active connection for user {user_id} — message dropped.")
            return

        # Send to ALL connections for this user (global WS + chat WS + etc.)
        dead = []
        for ws in sockets:
            if ws.client_state != WebSocketState.CONNECTED:
                dead.append(ws)
                continue
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                print(f"[WS] Send failed for user {user_id}: {e}")
                dead.append(ws)

        # Clean up dead sockets
        if dead:
            self.active_connections[user_id] = [
                ws for ws in sockets if ws not in dead
            ]
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        print(f"[WS] Sent '{message.get('type')}' to user {user_id} ({len(sockets) - len(dead)} conns)")

    async def send_to_user(self, user_id: str, message: dict):
        """Convenience alias supporting send_to_user(user_id, message) order."""
        await self.send_personal_message(message, user_id)

notifier = ConnectionManager()
