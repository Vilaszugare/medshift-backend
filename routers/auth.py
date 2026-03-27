from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
from models import TechnicianProfile, ManagerProfile, Hospital
from schemas import TechnicianRegisterRequest, LoginRequest, ManagerRegisterRequest
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

@router.post("/register/manager", status_code=status.HTTP_201_CREATED)
def register_manager(manager_data: ManagerRegisterRequest, db: Session = Depends(get_db)):
    # Check if email exists in ManagerProfile
    if db.query(ManagerProfile).filter(ManagerProfile.email == manager_data.email).first():
        raise HTTPException(status_code=400, detail="Manager email already registered")
    
    # Find or create Hospital
    hospital = db.query(Hospital).filter(Hospital.name == manager_data.hospital_name).first()
    if not hospital:
        hospital = Hospital(
            name=manager_data.hospital_name,
            address=manager_data.hospital_address,
            is_verified=True # Auto-verify for now as per seed patterns
        )
        db.add(hospital)
        db.commit()
        db.refresh(hospital)
    
    # Hash password using bcrypt for managers (more secure, consistent with seed_managers.py)
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(manager_data.password.encode('utf-8'), salt).decode('utf-8')
    
    # Create ManagerProfile
    new_manager = ManagerProfile(
        email=manager_data.email,
        password_hash=hashed_password,
        hospital_id=hospital.id,
        first_name=manager_data.first_name,
        last_name=manager_data.last_name,
        job_title=manager_data.job_title or "Hospital Manager",
        mobile_number=manager_data.mobile_number
    )
    db.add(new_manager)
    db.commit()
    db.refresh(new_manager)
    
    return {
        "message": "Manager registered successfully",
        "user": {
            "id": str(new_manager.id),
            "email": new_manager.email,
            "full_name": f"{new_manager.first_name} {new_manager.last_name}",
            "role": "manager",
            "hospital": hospital.name
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
