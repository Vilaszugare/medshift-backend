import sys
from sqlalchemy.orm import Session
import bcrypt
from database import SessionLocal, engine, Base
from models import Hospital, ManagerProfile

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def seed_managers():
    db: Session = SessionLocal()
    
    managers_data = [
        {"email": "vil@zu.com", "password": "vil", "name": "Vilas Manager", "hospital": "Nashik Lifeline Hospital", "area": "Nashik"},
        {"email": "lakhan@gmail.com", "password": "lakhan", "name": "Lakhan Manager", "hospital": "City Care Medical Center", "area": "Pune"}
    ]
    
    for m in managers_data:
        manager = db.query(ManagerProfile).filter(ManagerProfile.email == m["email"]).first()
        if manager:
            print(f"Skipping {m['email']}, already exists.")
            continue
            
        print(f"Seeding {m['email']}...")
        
        # Check hospital
        hospital = db.query(Hospital).filter(Hospital.name == m["hospital"]).first()
        if not hospital:
            hospital = Hospital(name=m["hospital"], address=m["area"], is_verified=True)
            db.add(hospital)
            db.commit()
            db.refresh(hospital)
            
        first_name, last_name = m["name"].split(" ", 1) if " " in m["name"] else (m["name"], "")
        
        manager_profile = ManagerProfile(
            email=m["email"],
            password_hash=get_password_hash(m["password"]),
            hospital_id=hospital.id,
            first_name=first_name,
            last_name=last_name,
            job_title="Hospital Manager"
        )
        db.add(manager_profile)
        db.commit()
        
    print("Seeding complete.")
    db.close()

if __name__ == "__main__":
    seed_managers()
