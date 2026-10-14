# Entry point of the application
import os
import json
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from database import get_db, engine, SessionLocal
import models
from fastapi.middleware.cors import CORSMiddleware
from routers import manager_dashboard, manager_actions, auth, technician_actions, messages
from fastapi import WebSocket, WebSocketDisconnect
from websocket_manager import notifier
from uuid import UUID

load_dotenv()

# ── Create all tables that are defined in models.py but missing in the DB ──────
# This is idempotent (safe to run every time) — it only creates tables that
# don't exist yet and never drops or modifies existing data.
models.Base.metadata.create_all(bind=engine)

# ── Seed suggested replies (idempotent — only inserts if the role has no rows) ──
def seed_suggested_replies():
    db = SessionLocal()
    try:
        # Manager replies
        if db.query(models.SuggestedReply).filter(models.SuggestedReply.role == "manager").count() == 0:
            for text in [
                "Approved. Please arrive 15 mins early.",
                "I will call you shortly to discuss.",
                "Please ensure your certifications are uploaded.",
                "Thank you for applying. We'll confirm soon.",
                "Kindly check in at the reception on arrival.",
            ]:
                db.add(models.SuggestedReply(role="manager", content=text))

        # Technician replies
        if db.query(models.SuggestedReply).filter(models.SuggestedReply.role == "technician").count() == 0:
            for text in [
                "Thank you! I will arrive 15 mins early.",
                "Understood. See you then.",
                "Could you please provide parking instructions?",
                "I am on my way.",
            ]:
                db.add(models.SuggestedReply(role="technician", content=text))

        db.commit()
    finally:
        db.close()

seed_suggested_replies()

app = FastAPI(title="MedShift API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "https://medmis.vercel.app",
        "https://lics-fry.loca.lt",
        "capacitor://localhost",
        "http://localhost",
        "https://localhost"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(manager_dashboard.router)
app.include_router(manager_actions.router)
app.include_router(technician_actions.router)
app.include_router(messages.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the MedShift API"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend is awake"}

@app.get("/api/states")
def get_indian_states(db: Session = Depends(get_db)):
    states = db.query(models.IndianState).order_by(models.IndianState.name).all()
    return {"states": [s.name for s in states]}


# ── Cloudflare TURN Credentials Proxy ──────────────────────────────────────────
@app.get("/api/turn-credentials")
async def get_turn_credentials():
    key_id = os.getenv("CLOUDFLARE_TURN_KEY_ID")
    api_token = os.getenv("CLOUDFLARE_TURN_API_TOKEN")
    if not key_id or not api_token:
        return JSONResponse(
            status_code=500,
            content={"error": "TURN credentials not configured on the server."},
        )
    url = f"https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}/credentials"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                json={"ttl": 86400},
            )
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"Cloudflare TURN API error: {e.response.text}"},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to fetch TURN credentials: {str(e)}"},
        )


# ── Helper: verify user_id exists in the database ─────────────────────────────
def _verify_user_id(user_id: str) -> dict | None:
    """
    Check if user_id belongs to a registered Manager or Technician.
    Returns a dict with user info or None if not found.
    Returns a fallback dict if the DB is unreachable (to avoid blocking WS).
    """
    # Try UUID parsing first (fast, no DB needed)
    try:
        uid = UUID(user_id)
    except (ValueError, AttributeError):
        print(f"[WS Auth] Invalid UUID format: {user_id}")
        return None

    db = SessionLocal()
    try:
        # Check manager profiles
        manager = db.query(models.ManagerProfile).filter(
            models.ManagerProfile.id == uid
        ).first()
        if manager:
            return {
                "id": str(manager.id),
                "name": f"{manager.first_name} {manager.last_name}".strip(),
                "role": "manager",
            }

        # Check technician profiles
        tech = db.query(models.TechnicianProfile).filter(
            models.TechnicianProfile.id == uid
        ).first()
        if tech:
            return {
                "id": str(tech.id),
                "name": tech.full_name,
                "role": "technician",
            }

        print(f"[WS Auth] User not found in DB: {user_id}")
        return None
    except Exception as e:
        # DB might be unreachable — allow connection with fallback name
        # so the app doesn't break when the remote DB is slow/down
        print(f"[WS Auth] DB error during user verification (allowing anyway): {e}")
        return {
            "id": user_id,
            "name": "MedShift User",
            "role": "unknown",
        }
    finally:
        db.close()


@app.websocket("/ws/notifications/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    # ── Authenticate: verify user_id exists in the database ──
    user_info = _verify_user_id(user_id)
    if user_info is None:
        # Must accept() before close() in FastAPI WebSocket
        await websocket.accept()
        await websocket.close(code=4001, reason="Invalid user ID")
        print(f"[WS] Rejected connection for unknown user_id: {user_id}")
        return

    await notifier.connect(websocket, user_id)
    print(f"[WS] Authenticated: {user_info['name']} ({user_info['role']})")

    try:
        while True:
            raw = await websocket.receive_text()
            # ── WebRTC signaling relay ─────────────────────────────────
            try:
                data = json.loads(raw)
                msg_type = data.get("type", "")
                target = data.get("target")
                if msg_type in (
                    "call-offer", "call-answer",
                    "ice-candidate", "call-hangup", "call-reject",
                ) and target:
                    # Stamp the sender and their name, then forward to target
                    data["from"] = user_id
                    data["callerName"] = user_info["name"]
                    await notifier.send_personal_message(data, target)
            except (json.JSONDecodeError, ValueError):
                pass  # ignore non-JSON frames (keep-alive pings, etc.)
    except WebSocketDisconnect:
        # Pass the specific websocket so only THIS connection is removed
        notifier.disconnect(user_id, websocket)


# ── Check if a user is currently online ────────────────────────────────────────
@app.get("/api/user-status/{user_id}")
def get_user_status(user_id: str):
    online = notifier.is_user_online(user_id)
    return {"user_id": user_id, "online": online}


@app.get("/api/notifications/{user_id}")
def get_notifications(user_id: str, db: Session = Depends(get_db)):
    notifs = db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    ).order_by(models.Notification.created_at.desc()).all()
    
    return [
        {
            "id": str(n.id),
            "title": n.title,
            "body": n.body,
            "icon": n.icon,
            "color": n.color,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat()
        } for n in notifs
    ]
