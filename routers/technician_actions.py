from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
import schemas
from uuid import UUID
from websocket_manager import notifier

router = APIRouter(prefix="/api/technician", tags=["Technician Actions"])

def get_current_tech_id(db: Session = Depends(get_db)) -> str:
    tech = db.query(models.TechnicianProfile).first()
    if not tech:
        raise HTTPException(status_code=404, detail="No technician found in database to mock.")
    return str(tech.id)

@router.put("/{technician_id}/availability")
def update_availability(technician_id: UUID, payload: schemas.AvailabilityUpdate, db: Session = Depends(get_db)):
    tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician not found")
        
    tech.is_available = payload.is_available
    db.commit()
    db.refresh(tech)
    
    return {"message": "Availability updated successfully", "is_available": tech.is_available}

@router.put("/profile")
def update_technician_profile(profile_data: schemas.TechnicianProfileUpdate, db: Session = Depends(get_db), user_id: str = Depends(get_current_tech_id)):
    tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == user_id).first()
    if not tech:
        raise HTTPException(status_code=404, detail="Technician profile not found")
    
    if profile_data.full_name is not None:
        tech.full_name = profile_data.full_name
    if profile_data.mobile_number is not None:
        tech.mobile_number = profile_data.mobile_number
    if profile_data.bio is not None:
        tech.bio = profile_data.bio
    if profile_data.specialty is not None:
        tech.specialty = profile_data.specialty
    if profile_data.machine_skills is not None:
        tech.machine_skills = profile_data.machine_skills
    if profile_data.certifications_list is not None:
        tech.certifications_list = profile_data.certifications_list
    if profile_data.experience_years is not None:
        tech.experience_years = profile_data.experience_years
    if profile_data.country is not None:
        tech.country = profile_data.country
    if profile_data.state is not None:
        tech.state = profile_data.state
    if profile_data.district is not None:
        tech.district = profile_data.district
    if profile_data.city is not None:
        tech.city = profile_data.city
    if profile_data.home_address is not None:
        tech.home_address = profile_data.home_address
        
    db.commit()
    db.refresh(tech)
    
    return {
        "message": "Success",
        "profile": {
            "name": tech.full_name,
            "mobile_number": tech.mobile_number,
            "role": "technician",
            "bio": tech.bio,
            "specialty": tech.specialty,
            "machine_skills": tech.machine_skills,
            "certifications_list": tech.certifications_list,
            "experience_years": tech.experience_years,
            "country": tech.country,
            "state": tech.state,
            "district": tech.district,
            "city": tech.city,
            "home_address": tech.home_address
        }
    }

@router.post("/shifts/{shift_id}/apply")
async def apply_for_shift(shift_id: UUID, apply_data: schemas.ShiftApplySchema, db: Session = Depends(get_db)):
    shift = db.query(models.Shift).filter(models.Shift.id == shift_id).first()
    if not shift:
        raise HTTPException(status_code=404, detail="Shift not found")
        
    # check if already applied
    existing = db.query(models.ShiftAssignment).filter(
        models.ShiftAssignment.shift_id == shift_id,
        models.ShiftAssignment.technician_id == apply_data.technician_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Already applied to this shift")
        
    new_assignment = models.ShiftAssignment(
        shift_id=shift_id,
        technician_id=apply_data.technician_id,
        status=models.ShiftAssignmentStatus.pending
    )
    db.add(new_assignment)
    db.commit()
    db.refresh(new_assignment)

    # Create Notification for the Manager
    tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == apply_data.technician_id).first()
    tech_name = tech.full_name if tech else "A technician"
    
    new_notif = models.Notification(
        user_id=shift.manager_id,
        title="New Applicant",
        body=f"{tech_name} applied for your shift: {shift.title}",
        icon="user",
        color="#0D9488" # Teal
    )
    db.add(new_notif)
    db.commit()
    db.refresh(new_notif)

    # Insert a canned intro Message from technician → manager
    new_message = models.Message(
        shift_id=shift_id,
        sender_id=apply_data.technician_id,
        receiver_id=shift.manager_id,
        content=f"Hi sir, I am {tech_name} and I am ready to work your shift for {shift.title}. Please approve me.",
        is_read=False,
    )
    db.add(new_message)
    db.commit()

    # Push notification via WebSocket
    notification_dict = {
        "id": str(new_notif.id),
        "title": new_notif.title,
        "body": new_notif.body,
        "icon": new_notif.icon,
        "color": new_notif.color,
        "is_read": False,
        "tag": "New",
        "time": "Just now"
    }
    await notifier.send_personal_message(notification_dict, str(shift.manager_id))
    
    return {
        "message": "Applied successfully",
        "assignment_id": new_assignment.id,
        "status": new_assignment.status.value
    }

