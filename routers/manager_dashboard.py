from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List

from database import get_db
import models
import schemas

router = APIRouter(prefix="/api/dashboard", tags=["Manager Dashboard"])

# Replaced aggressive mock with optional query parameter
def get_current_user_id(manager_id: str = None, db: Session = Depends(get_db)) -> str:
    if manager_id:
        return manager_id
    manager = db.query(models.ManagerProfile).first()
    if not manager:
        raise HTTPException(status_code=404, detail="No manager found in database to mock.")
    return str(manager.id)

def calculate_duration(start, end) -> float:
    return round((end - start).total_seconds() / 3600.0, 2)

@router.get("/manager", response_model=schemas.ManagerDashboardResponse)
def get_manager_dashboard(db: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == user_id).first()
    if not manager:
        raise HTTPException(status_code=404, detail="Manager profile not found")
        
    hospital = manager.hospital
    
    # Key Metrics
    active_shifts_count = db.query(models.Shift).filter(
        models.Shift.manager_id == manager.id,
        models.Shift.status == models.ShiftStatus.searching
    ).count()
    
    historical_hires = db.query(models.Shift).filter(
        models.Shift.manager_id == manager.id,
        models.Shift.status == models.ShiftStatus.completed
    ).count()
    
    # Fetch Posted Shifts for this manager
    shifts_query = db.query(models.Shift).filter(
        models.Shift.manager_id == manager.id
    ).order_by(models.Shift.start_time.desc()).all()
    
    posted_shifts = []
    for s in shifts_query:
        assignments = db.query(models.ShiftAssignment).filter(
            models.ShiftAssignment.shift_id == s.id,
            models.ShiftAssignment.status == models.ShiftAssignmentStatus.accepted
        ).all()
        
        pending_count = db.query(models.ShiftAssignment).filter(
            models.ShiftAssignment.shift_id == s.id,
            models.ShiftAssignment.status == models.ShiftAssignmentStatus.pending
        ).count()

        tech_name = None
        tech_phone = None
        tech_id = None
        accepted_techs = []
        if assignments:
            for assign in assignments:
                tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == assign.technician_id).first()
                if tech:
                    if tech_id is None:
                        tech_id = tech.id
                        tech_name = tech.full_name
                        tech_phone = tech.mobile_number
                    
                    accepted_techs.append(schemas.ShiftApplicantSchema(
                        id=assign.id,
                        technician_id=assign.technician_id,
                        name=tech.full_name,
                        rating=tech.rating,
                        status=assign.status.value,
                        applied_at=assign.created_at
                    ))

        posted_shifts.append(schemas.ShiftBase(
            id=s.id,
            title=s.title,
            department=s.department,
            start_time=s.start_time,
            end_time=s.end_time,
            hourly_rate=s.hourly_rate,
            status=s.status.value,
            is_urgent=s.is_urgent,
            duration=s.end_time and round((s.end_time - s.start_time).total_seconds() / 3600.0, 2) or 0.0,
            technician_id=tech_id,
            technician_name=tech_name,
            technician_phone=tech_phone,
            max_technicians=s.max_technicians or 1,
            pending_count=pending_count,
            accepted_count=len(assignments),
            accepted_technicians=accepted_techs
        ))

    return schemas.ManagerDashboardResponse(
        profile=schemas.ManagerProfileSchema(
            name=f"{manager.first_name} {manager.last_name}",
            role=manager.job_title or "Hospital Manager",
            hospital_name=hospital.name,
            hospital_area=hospital.address,
            is_verified=hospital.is_verified
        ),
        stats=schemas.ManagerStatsSchema(
            active_shifts=active_shifts_count,
            historical_hires=historical_hires,
            hospital_rating=4.8 # Simplified mock logic
        ),
        posted_shifts=posted_shifts,
    )

@router.put("/manager/profile", response_model=schemas.ManagerDashboardResponse)
def update_manager_profile(profile_data: schemas.ManagerProfileUpdate, manager_id: str = None, db: Session = Depends(get_db)):
    if manager_id:
        manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == manager_id).first()
    else:
        manager = db.query(models.ManagerProfile).first()
        
    if not manager:
        raise HTTPException(status_code=404, detail="Manager profile not found")
        
    hospital = db.query(models.Hospital).filter(models.Hospital.id == manager.hospital_id).first()
    
    if profile_data.full_name:
        parts = profile_data.full_name.split(" ", 1)
        manager.first_name = parts[0]
        if len(parts) > 1:
            manager.last_name = parts[1]
    
    if profile_data.mobile_number is not None:
        manager.mobile_number = profile_data.mobile_number
    if profile_data.job_title is not None:
        manager.job_title = profile_data.job_title
        
    if hospital:
        if profile_data.hospital_name is not None:
            hospital.name = profile_data.hospital_name
        if profile_data.hospital_address is not None:
            hospital.address = profile_data.hospital_address
        if profile_data.facilities is not None:
            hospital.facilities = profile_data.facilities
        if profile_data.certifications is not None:
            hospital.certifications = profile_data.certifications
            
    db.commit()
    
    # Return updated dashboard
    return get_manager_dashboard(db, str(manager.id))
