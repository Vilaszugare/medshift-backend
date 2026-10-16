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
from fastapi.staticfiles import StaticFiles
from routers import manager_dashboard, manager_actions, auth, technician_actions, messages, otp, community
from fastapi import WebSocket, WebSocketDisconnect
from websocket_manager import notifier
from uuid import UUID
from pydantic import BaseModel
from typing import Optional, List

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

# ── Firebase Admin SDK Initialization ──────────────────────────────────────────
try:
    import firebase_admin
    from firebase_admin import credentials

    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
    if cred_path and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print(f"[Firebase] Initialized with credentials from: {cred_path}")
    else:
        try:
            firebase_admin.initialize_app()
            print("[Firebase] Initialized with default application credentials.")
        except Exception:
            print("[Firebase] FIREBASE_CREDENTIALS_PATH not configured. Set path in .env to enable FCM push.")
except Exception as e:
    print(f"[Firebase] Initialization note: {e}")

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
        "https://localhost",
        "https://medshift-backend-1.onrender.com"
    ],
    allow_origin_regex=r".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for post image uploads
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(os.path.join(UPLOAD_DIR, "posts"), exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(manager_dashboard.router)
app.include_router(manager_actions.router)
app.include_router(technician_actions.router)
app.include_router(messages.router)
app.include_router(otp.router)
app.include_router(community.router)

@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"message": "Welcome to the MedShift API"}

@app.api_route("/api/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok", "message": "Backend is awake"}

@app.get("/api/states")
def get_indian_states(db: Session = Depends(get_db)):
    states = db.query(models.IndianState).order_by(models.IndianState.name).all()
    return {"states": [s.name for s in states]}


# ── FCM Push Notification Token Storage & High-Priority Call Dispatch ────────
class FCMTokenUpdate(BaseModel):
    user_id: str
    fcm_token: str
    platform: str | None = None

user_fcm_tokens: dict[str, str] = {}

@app.post("/api/users/update-fcm-token")
def update_fcm_token(payload: FCMTokenUpdate, db: Session = Depends(get_db)):
    user_fcm_tokens[payload.user_id] = payload.fcm_token
    try:
        uid = UUID(payload.user_id)
        # Try technician profile
        tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == uid).first()
        if tech:
            tech.fcm_token = payload.fcm_token
            db.commit()
        else:
            # Try manager profile
            mgr = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == uid).first()
            if mgr:
                mgr.fcm_token = payload.fcm_token
                db.commit()
    except Exception as e:
        print(f"[FCM] Could not persist token to database: {e}")

    print(f"[FCM] Stored token for user {payload.user_id} on {payload.platform}")
    return {"status": "ok", "message": "FCM device token registered"}


def send_call_push_notification(target_user_id: str, call_id: str, caller_name: str):
    """
    Dispatch a High-Priority FCM Data Message to wake the callee device
    when a call-offer is initiated. Strictly uses a 'data' payload (no 'notification' block)
    so IncomingCallKit handles the lock-screen ringing UI natively without system tray banners.
    """
    token = user_fcm_tokens.get(target_user_id)
    if not token:
        db = SessionLocal()
        try:
            uid = UUID(target_user_id)
            user_obj = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == uid).first()
            if not user_obj or not user_obj.fcm_token:
                user_obj = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == uid).first()
            if user_obj and user_obj.fcm_token:
                token = user_obj.fcm_token
                user_fcm_tokens[target_user_id] = token
        except Exception as e:
            print(f"[FCM] Token lookup error for user {target_user_id}: {e}")
        finally:
            db.close()

    if not token:
        print(f"[FCM] No token found for user {target_user_id} — skipping FCM push.")
        return

    try:
        import firebase_admin
        from firebase_admin import messaging

        message = messaging.Message(
            data={
                "type": "incoming_call",
                "callId": str(call_id),
                "callerName": str(caller_name),
            },
            android=messaging.AndroidConfig(
                priority="high",
            ),
            token=token,
        )
        response = messaging.send(message)
        print(f"[FCM] High-priority call push dispatched to {target_user_id}: {response}")
    except Exception as e:
        print(f"[FCM] Error dispatching push to {target_user_id}: {e}")


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
            # ── WebRTC signaling relay & keep-alive ────────────────────
            try:
                data = json.loads(raw)
                msg_type = data.get("type", "")
                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                    continue

                target = data.get("target")
                if msg_type in (
                    "call-offer", "call-answer",
                    "ice-candidate", "call-hangup", "call-reject", "call-video-state",
                ) and target:
                    # Stamp the sender and their name, then forward to target
                    data["from"] = user_id
                    data["callerName"] = user_info["name"]
                    await notifier.send_personal_message(data, target)

                    # Dispatch high-priority FCM data push to wake callee on initial offer only
                    if msg_type == "call-offer" and not data.get("renegotiate"):
                        call_id = data.get("callId") or user_id
                        send_call_push_notification(target, str(call_id), user_info["name"])
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


class MarkNotificationsReadRequest(BaseModel):
    user_id: Optional[str] = None
    notification_id: Optional[str] = None
    notification_ids: Optional[List[str]] = None


@app.put("/api/notifications/read")
def mark_notifications_read(
    payload: Optional[MarkNotificationsReadRequest] = None,
    user_id: Optional[str] = Query(None),
    notification_id: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    target_user_id = (payload.user_id if payload and payload.user_id else None) or user_id
    target_notif_id = (payload.notification_id if payload and payload.notification_id else None) or notification_id
    target_notif_ids = payload.notification_ids if payload and payload.notification_ids else None

    # Case 1: Specific notification ID
    if target_notif_id:
        db.query(models.Notification).filter(
            models.Notification.id == target_notif_id
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
        return {"status": "success", "message": f"Notification {target_notif_id} marked as read"}

    # Case 2: List of notification IDs
    if target_notif_ids:
        db.query(models.Notification).filter(
            models.Notification.id.in_(target_notif_ids)
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
        return {"status": "success", "message": f"{len(target_notif_ids)} notifications marked as read"}

    # Case 3: All notifications for user
    if target_user_id:
        db.query(models.Notification).filter(
            models.Notification.user_id == target_user_id,
            models.Notification.is_read == False
        ).update({"is_read": True}, synchronize_session=False)
        db.commit()
        return {"status": "success", "message": f"All notifications marked as read for user {target_user_id}"}

    return {"status": "ignored", "message": "No user_id or notification_id provided"}


@app.put("/api/notifications/{user_id}/read")
def mark_all_user_notifications_read(user_id: str, db: Session = Depends(get_db)):
    db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.is_read == False
    ).update({"is_read": True}, synchronize_session=False)
    db.commit()
    return {"status": "success", "message": f"All notifications marked as read for user {user_id}"}


@app.delete("/api/notifications/{user_id}")
def clear_user_notifications(user_id: str, db: Session = Depends(get_db)):
    db.query(models.Notification).filter(
        models.Notification.user_id == user_id
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "success", "message": f"Notifications cleared for user {user_id}"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)

