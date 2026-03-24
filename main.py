# Entry point of the application
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import get_db, engine, SessionLocal
import models
from fastapi.middleware.cors import CORSMiddleware
from routers import manager_dashboard, manager_actions, auth, technician_actions, messages
from fastapi import WebSocket, WebSocketDisconnect
from websocket_manager import notifier

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


@app.websocket("/ws/notifications/{user_id}")
async def websocket_notifications(websocket: WebSocket, user_id: str):
    await notifier.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        notifier.disconnect(user_id)


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
