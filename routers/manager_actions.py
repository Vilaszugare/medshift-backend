from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
import uuid
import asyncio

from database import get_db
from datetime import datetime

import models
import schemas
from websocket_manager import notifier

router = APIRouter(prefix="/api", tags=["Manager Actions"])

# Mock User ID temporarily. In a real system this extracts UUID from JWT.
def get_current_user_id() -> UUID:
    # We will use a mock valid UUID for testing when auth is disabled.
    return uuid.UUID("11111111-1111-1111-1111-111111111111")

@router.post("/withdraw")
def mock_withdraw():
    pass

@router.put("/shifts/{shift_id}/complete")
def complete_shift(shift_id: UUID, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    shift.status = models.ShiftStatus.completed
    db.commit()
    db.refresh(shift)
    return {"message": "Shift marked as complete", "status": shift.status.value}

@router.put("/shifts/{shift_id}/finalize")
def finalize_shift(shift_id: UUID, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
        
    # Check if there are accepted users
    accepted_count = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.shift_id == shift_id,
        models.ShiftAssignment.status == models.ShiftAssignmentStatus.accepted
    ).count()
    
    if accepted_count == 0:
        raise HTTPException(status_code=400, detail="Cannot finalize shift without accepted technicians")
        
    shift.status = models.ShiftStatus.filled
    
    # Reject remaining pending assignments
    pending_assignments = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.shift_id == shift_id,
        models.ShiftAssignment.status == models.ShiftAssignmentStatus.pending
    ).all()
    for pa in pending_assignments:
        pa.status = models.ShiftAssignmentStatus.rejected
        
    db.commit()
    db.refresh(shift)
    return {"message": "Shift finalized and assigned", "status": shift.status.value, "accepted_count": accepted_count}

@router.put("/shifts/{shift_id}/archive")
def archive_shift(shift_id: UUID, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    shift.status = models.ShiftStatus.archived
    db.commit()
    db.refresh(shift)
    return {"message": "Shift permanently archived", "status": shift.status.value}

@router.put("/shifts/{shift_id}/cancel")
def cancel_shift(shift_id: UUID, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
    shift.status = models.ShiftStatus.cancelled
    db.query(models.ShiftAssignment).filter(models.ShiftAssignment.shift_id == shift_id).delete()
    db.commit()
    return {"message": "Shift cancelled explicitly", "status": shift.status.value}

@router.post("/shifts", response_model=schemas.ShiftBase)
def create_shift(shift_in: schemas.ShiftCreate, db: Session = Depends(get_db)):
    new_shift = models.Shift(
        manager_id=shift_in.manager_id,
        title=shift_in.title,
        department=shift_in.department,
        start_time=shift_in.start_time,
        end_time=shift_in.end_time,
        hourly_rate=shift_in.hourly_rate,
        is_urgent=shift_in.is_urgent,
        status=models.ShiftStatus.searching
    )
    
    db.add(new_shift)
    db.commit()
    db.refresh(new_shift)
    
    # Optional logic: duration mapper required by our response schema
    duration = 0.0
    if new_shift.end_time:
        duration = round((new_shift.end_time - new_shift.start_time).total_seconds() / 3600.0, 2)
        
    return schemas.ShiftBase(
        id=new_shift.id,
        title=new_shift.title,
        department=new_shift.department,
        start_time=new_shift.start_time,
        end_time=new_shift.end_time,
        hourly_rate=new_shift.hourly_rate,
        status=new_shift.status.value,
        is_urgent=new_shift.is_urgent,
        duration=duration
    )

@router.post("/community/posts", response_model=schemas.CommunityPostBase)
def create_community_post(post_in: schemas.CommunityPostCreate, db: Session = Depends(get_db)):
    is_manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == post_in.author_id).first()
    new_post = models.CommunityPost(
        manager_id=post_in.author_id if is_manager else None,
        technician_id=post_in.author_id if not is_manager else None,
        content=post_in.content,
        image_url=post_in.image_url
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    
    return new_post

@router.get("/community/posts")
def get_community_posts(db: Session = Depends(get_db)):
    posts = db.query(models.CommunityPost).order_by(models.CommunityPost.created_at.desc()).all()
    result = []
    for post in posts:
        author_name = "Unknown"
        initials = "U"
        role = "User"
        
        if post.manager_id:
            manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == post.manager_id).first()
            if manager:
                author_name = f"{manager.first_name} {manager.last_name}"
                initials = "".join([n[0] for n in author_name.split() if n]) if author_name else "M"
                hospital = db.query(models.Hospital).filter(models.Hospital.id == manager.hospital_id).first()
                hospital_name = hospital.name if hospital else "Hospital"
                role_title = manager.job_title or "CMO"
                role = f"{role_title} · {hospital_name}"
        elif post.technician_id:
            tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == post.technician_id).first()
            if tech:
                author_name = tech.full_name
                initials = "".join([n[0] for n in author_name.split() if n]) if author_name else "T"
                role = tech.title or "Technician"
                    
        result.append({
            "id": post.id,
            "author": author_name,
            "initials": initials,
            "role": role,
            "content": post.content,
            "created_at": post.created_at,
            "image_url": post.image_url
        })
    return result

@router.get("/shifts/available")
def get_available_shifts(db: Session = Depends(get_db)):
    shifts = db.query(models.Shift).filter(models.Shift.status == models.ShiftStatus.searching).order_by(models.Shift.created_at.desc()).all()
    result = []
    for shift in shifts:
        hospital_name = "Unknown Hospital"
        manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == shift.manager_id).first()
        if manager:
            hospital = db.query(models.Hospital).filter(models.Hospital.id == manager.hospital_id).first()
            if hospital:
                hospital_name = hospital.name
                
        duration = 0.0
        if shift.end_time:
            duration = round((shift.end_time - shift.start_time).total_seconds() / 3600.0, 2)
            
        result.append({
            "id": shift.id,
            "title": shift.title,
            "department": shift.department,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "hourly_rate": shift.hourly_rate,
            "is_urgent": shift.is_urgent,
            "status": shift.status.value,
            "hospital": hospital_name,
            "duration": duration
        })
    return result

@router.get("/shifts/{shift_id}/applicants")
def get_shift_applicants(shift_id: UUID, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
        
    assignments = db.query(models.ShiftAssignment).filter(models.ShiftAssignment.shift_id == shift_id).all()
    result = []
    for assign in assignments:
        tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == assign.technician_id).first()
        if tech:
            result.append({
                "id": assign.id,
                "technician_id": assign.technician_id,
                "name": tech.full_name,
                "rating": tech.rating,
                "status": assign.status.value,
                "applied_at": assign.created_at
            })
    return result

@router.put("/shifts/{shift_id}/applicants/{technician_id}/accept")
def accept_applicant(shift_id: UUID, technician_id: UUID, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
        
    assignment = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.shift_id == shift_id,
        models.ShiftAssignment.technician_id == technician_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Application not found")
        
    if assignment.status == models.ShiftAssignmentStatus.accepted:
        return {"message": "Already accepted"}

    assignment.status = models.ShiftAssignmentStatus.accepted
    assignment.accepted_at = datetime.utcnow()

    # ── Notify the technician ────────────────────────────────────────────────
    notif = models.Notification(
        user_id=technician_id,
        title="🎉 Shift Approved!",
        body=f"The manager accepted your application for: {shift.title}",
        icon="check",
        color="#0D9488",
    )
    db.add(notif)
    db.commit()
    db.refresh(assignment)
    db.refresh(notif)

    # Fire-and-forget WebSocket push to the technician
    import asyncio
    notif_payload = {
        "id": str(notif.id),
        "title": notif.title,
        "body": notif.body,
        "icon": notif.icon,
        "color": notif.color,
        "is_read": False,
    }
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(notifier.send_to_user(str(technician_id), notif_payload))
    except Exception:
        pass  # WS push is best-effort

    return {"message": "Applicant accepted successfully", "status": assignment.status.value}

@router.put("/shifts/{shift_id}/applicants/{technician_id}/reject")
def reject_applicant(shift_id: UUID, technician_id: UUID, db: Session = Depends(get_db)):
    assignment = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.shift_id == shift_id,
        models.ShiftAssignment.technician_id == technician_id
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Application not found")
        
    assignment.status = models.ShiftAssignmentStatus.rejected
    db.commit()
    db.refresh(assignment)
    
    return {"message": "Applicant rejected successfully", "status": assignment.status.value}

