from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import TechnicianProfile, ManagerProfile
from schemas import TechnicianRegisterRequest, LoginRequest
import hashlib
import uuid
import bcrypt
from fastapi import APIRouter

router = APIRouter(prefix="/api/auth", tags=["auth"])

def verify_password(plain_password, hashed_password):
    if len(hashed_password) == 64: # SHA256 for older mock accounts
        return hashlib.sha256(plain_password.encode()).hexdigest() == hashed_password
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    # Hash for demo purposes (newly created technicians keep this fallback or we upgrade them too)
    return hashlib.sha256(password.encode()).hexdigest()

@router.post("/register/technician", status_code=status.HTTP_201_CREATED)
def register_technician(tech_data: TechnicianRegisterRequest, db: Session = Depends(get_db)):
    # Check if email exists
    if db.query(TechnicianProfile).filter(TechnicianProfile.email == tech_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # Check if mobile exists
    if db.query(TechnicianProfile).filter(TechnicianProfile.mobile_number == tech_data.mobile_number).first():
        raise HTTPException(status_code=400, detail="Mobile number already registered")
    
    # Create Profile
    new_profile = TechnicianProfile(
        email=tech_data.email,
        password_hash=get_password_hash(tech_data.password),
        full_name=tech_data.full_name,
        mobile_number=tech_data.mobile_number,
        id_document_url=tech_data.id_document,
        certificate_url=tech_data.certificate,
        title="Unverified Technician",
        verification_status="pending"
    )
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    
    return {
        "message": "Technician registered successfully", 
        "user": {
            "id": str(new_profile.id), 
            "email": new_profile.email,
            "full_name": new_profile.full_name, 
            "role": "technician"
        }
    }

@router.post("/login")
def login_user(login_data: LoginRequest, db: Session = Depends(get_db)):
    if login_data.role == "manager":
        profile = db.query(ManagerProfile).filter(ManagerProfile.email == login_data.email).first()
        if not profile or not verify_password(login_data.password, profile.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials or unauthorized access")
        full_name = f"{profile.first_name} {profile.last_name}"
        return {
            "message": "Success", 
            "user": {
                "id": str(profile.id), 
                "email": profile.email,
                "full_name": full_name, 
                "role": "manager"
            }
        }
    else:
        profile = db.query(TechnicianProfile).filter(TechnicianProfile.email == login_data.email).first()
        if not profile or not verify_password(login_data.password, profile.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials or unauthorized access")
        return {
            "message": "Success", 
            "user": {
                "id": str(profile.id), 
                "email": profile.email,
                "full_name": profile.full_name, 
                "role": "technician"
            }
        }
