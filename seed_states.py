import uuid
from sqlalchemy.orm import Session
from database import engine, SessionLocal, Base
import models

# Create all tables (in case indian_states is new)
models.Base.metadata.create_all(bind=engine)

STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", 
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", 
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", 
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", 
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", 
    "Uttarakhand", "West Bengal"
]

def seed_states():
    db: Session = SessionLocal()
    try:
        for state_name in STATES:
            # Check if exists
            existing = db.query(models.IndianState).filter(models.IndianState.name == state_name).first()
            if not existing:
                new_state = models.IndianState(id=uuid.uuid4(), name=state_name)
                db.add(new_state)
        db.commit()
        print("Successfully seeded 28 Indian States.")
    except Exception as e:
        print(f"Error seeding states: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_states()
