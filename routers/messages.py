from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
from pydantic import BaseModel
from uuid import UUID
import uuid as uuid_module
from datetime import datetime
from websocket_manager import notifier

router = APIRouter(prefix="/api/messages", tags=["Messages"])


# ─── Schemas ──────────────────────────────────────────────────────────────────
class ReplyPayload(BaseModel):
    sender_id: UUID
    receiver_id: UUID
    shift_id: UUID
    content: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/manager/{manager_id}")
def get_messages_for_manager(manager_id: UUID, db: Session = Depends(get_db)):
    """Fetch all messages where the manager is the receiver — single JOIN query."""
    from sqlalchemy import UUID as SQLUUID

    rows = (
        db.query(
            models.Message,
            models.TechnicianProfile.full_name.label("sender_name"),
            models.Shift.title.label("shift_title"),
        )
        .outerjoin(
            models.TechnicianProfile,
            models.TechnicianProfile.id == models.Message.sender_id,
        )
        .outerjoin(models.Shift, models.Shift.id == models.Message.shift_id)
        .filter(models.Message.receiver_id == manager_id)
        .order_by(models.Message.created_at.desc())
        .all()
    )

    return [
        {
            "id": str(m.id),
            "shift_id": str(m.shift_id),
            "shift_title": shift_title or "Unknown Shift",
            "sender_id": str(m.sender_id),
            "sender_name": sender_name or "Unknown Technician",
            "receiver_id": str(m.receiver_id),
            "content": m.content,
            "is_read": m.is_read,
            "created_at": m.created_at.isoformat(),
        }
        for m, sender_name, shift_title in rows
    ]



@router.get("/suggested-replies/manager")
def get_suggested_replies_manager(db: Session = Depends(get_db)):
    """Fetch all canned suggested replies for the manager role."""
    replies = (
        db.query(models.SuggestedReply)
        .filter(models.SuggestedReply.role == "manager")
        .all()
    )
    return [{"id": str(r.id), "content": r.content} for r in replies]


@router.get("/suggested-replies/technician")
def get_suggested_replies_technician(db: Session = Depends(get_db)):
    """Fetch all canned suggested replies for the technician role."""
    replies = (
        db.query(models.SuggestedReply)
        .filter(models.SuggestedReply.role == "technician")
        .all()
    )
    return [{"id": str(r.id), "content": r.content} for r in replies]


@router.post("/reply")
def send_reply(payload: ReplyPayload, db: Session = Depends(get_db)):
    """Save a manager's reply message and notify the receiver."""
    new_msg = models.Message(
        shift_id=payload.shift_id,
        sender_id=payload.sender_id,
        receiver_id=payload.receiver_id,
        content=payload.content,
        is_read=False,
        created_at=datetime.utcnow(),
    )
    db.add(new_msg)

    # Mark the original message(s) from the other side as read
    db.query(models.Message).filter(
        models.Message.shift_id == payload.shift_id,
        models.Message.receiver_id == payload.sender_id,
        models.Message.sender_id == payload.receiver_id,
    ).update({"is_read": True})

    # Notify the receiver
    notif = models.Notification(
        user_id=payload.receiver_id,
        title="💬 New Message",
        body="You have a new message regarding your shift.",
        icon="check",
        color="#0D9488",
    )
    db.add(notif)
    db.commit()
    db.refresh(new_msg)

    # ── Real-time WebSocket push ──────────────────────────────────────────────
    # NOTE: send_reply is a SYNC route (runs in a threadpool).
    # We MUST use run_coroutine_threadsafe to schedule coroutines onto the
    # main async event loop — loop.create_task() silently fails in sync context.
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        receiver_str = str(payload.receiver_id)

        # Push notification object
        asyncio.run_coroutine_threadsafe(
            notifier.send_personal_message(
                {
                    "type": "notification",
                    "id": str(notif.id),
                    "title": notif.title,
                    "body": notif.body,
                    "icon": notif.icon,
                    "color": notif.color,
                    "is_read": False,
                },
                receiver_str,
            ),
            loop,
        )

        # Push the actual message data so the chat thread updates instantly
        asyncio.run_coroutine_threadsafe(
            notifier.send_personal_message(
                {
                    "type": "new_message",
                    "message": {
                        "id": str(new_msg.id),
                        "shift_id": str(new_msg.shift_id),
                        "sender_id": str(new_msg.sender_id),
                        "receiver_id": str(new_msg.receiver_id),
                        "content": new_msg.content,
                        "is_read": new_msg.is_read,
                        "created_at": new_msg.created_at.isoformat(),
                    },
                },
                receiver_str,
            ),
            loop,
        )
    except Exception as e:
        print(f"[WS push error] {e}")

    return {"message": "Reply sent", "id": str(new_msg.id)}



@router.get("/technician/{tech_id}")
def get_messages_for_technician(tech_id: UUID, db: Session = Depends(get_db)):
    """
    Fetch the latest message per shift thread for a technician (as either
    sender or receiver), ordered newest-first — for the inbox list view.
    """
    msgs = (
        db.query(models.Message)
        .filter(
            (models.Message.sender_id == tech_id) | (models.Message.receiver_id == tech_id)
        )
        .order_by(models.Message.created_at.desc())
        .all()
    )

    # De-duplicate by shift_id: one entry per shift (the latest message)
    seen_shifts = set()
    results = []
    for m in msgs:
        shift_key = str(m.shift_id)
        if shift_key in seen_shifts:
            continue
        seen_shifts.add(shift_key)

        # Resolve the other party (manager)
        other_id = m.receiver_id if str(m.sender_id) == str(tech_id) else m.sender_id
        manager = db.query(models.ManagerProfile).filter(
            models.ManagerProfile.id == other_id
        ).first()
        if manager:
            manager_name = f"{manager.first_name} {manager.last_name}".strip() or "Manager"
        else:
            manager_name = "Manager"

        shift = db.query(models.Shift).filter(models.Shift.id == m.shift_id).first()
        shift_title = shift.title if shift else "Unknown Shift"

        results.append({
            "id": str(m.id),
            "shift_id": str(m.shift_id),
            "shift_title": shift_title,
            "sender_id": str(m.sender_id),
            "receiver_id": str(m.receiver_id),
            "manager_id": str(other_id),
            "manager_name": manager_name,
            "content": m.content,
            "is_read": m.is_read if str(m.receiver_id) == str(tech_id) else True,
            "created_at": m.created_at.isoformat(),
        })

    return results


@router.put("/{message_id}/read")
def mark_message_read(message_id: UUID, db: Session = Depends(get_db)):
    """Mark a single message as read."""
    msg = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    msg.is_read = True
    db.commit()
    return {"message": "Marked as read"}


@router.get("/thread/{shift_id}/{manager_id}/{technician_id}")
def get_thread(shift_id: UUID, manager_id: UUID, technician_id: UUID, db: Session = Depends(get_db)):
    """
    Fetch the full back-and-forth message thread between a manager and a
    technician for a specific shift, ordered oldest → newest.
    """
    msgs = (
        db.query(models.Message)
        .filter(
            models.Message.shift_id == shift_id,
            # Either direction: tech→manager or manager→tech
            (
                (models.Message.sender_id == technician_id) & (models.Message.receiver_id == manager_id)
                | (models.Message.sender_id == manager_id) & (models.Message.receiver_id == technician_id)
            ),
        )
        .order_by(models.Message.created_at.asc())
        .all()
    )

    return [
        {
            "id": str(m.id),
            "shift_id": str(m.shift_id),
            "sender_id": str(m.sender_id),
            "receiver_id": str(m.receiver_id),
            "content": m.content,
            "is_read": m.is_read,
            "created_at": m.created_at.isoformat(),
        }
        for m in msgs
    ]

