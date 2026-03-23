from database import SessionLocal
import models
import uuid

def seed():
    db = SessionLocal()
    mock_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    

        
    hosp = db.query(models.Hospital).first()
    if not hosp:
        hosp = models.Hospital(
            name="Apollo Regional Medical Center",
            address="Seattle, WA Core District",
            is_verified=True
        )
        db.add(hosp)
        db.commit()
        db.refresh(hosp)
        
    manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == mock_id).first()
    if not manager:
        manager = models.ManagerProfile(
            id=mock_id,
            email="mock_manager@medshift.com",
            password_hash="hashed_password",
            hospital_id=hosp.id,
            first_name="Dr. Sarah",
            last_name="Chen",
            job_title="Chief Medical Officer"
        )
        db.add(manager)
        db.commit()
        
    print("Successfully seeded the database with the mock manager 11111111-1111-1111-1111-111111111111!")

if __name__ == "__main__":
    seed()
