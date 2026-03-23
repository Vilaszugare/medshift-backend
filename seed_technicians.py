import uuid
from database import SessionLocal
from models import TechnicianProfile
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def seed_technicians():
    db = SessionLocal()
    try:
        techs_to_seed = [
            {"email": "vilas@zugare", "password": "vilas", "full_name": "Vilas", "mobile": "9998887701"},
            {"email": "lakhan@thakare", "password": "lakhan", "full_name": "Lakhan", "mobile": "9998887702"},
            {"email": "nisha@123", "password": "nisha", "full_name": "Nisha", "mobile": "9998887703"},
        ]

        for tech_data in techs_to_seed:
            existing_tech = db.query(TechnicianProfile).filter(TechnicianProfile.email == tech_data["email"]).first()
            if existing_tech:
                print(f"Tech {tech_data['email']} already exists. Skipping.")
                continue

            new_profile = TechnicianProfile(
                email=tech_data["email"],
                password_hash=get_password_hash(tech_data["password"]),
                full_name=tech_data["full_name"],
                mobile_number=tech_data["mobile"],
                title="Medical Technician",
                is_available=True,
                rating=4.8,
                total_shifts=0
            )
            db.add(new_profile)
            print(f"Created Technician: {tech_data['full_name']} ({tech_data['email']})")

        db.commit()
        print("\nSuccessfully seeded all dummy technicians!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding technicians: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    print("Starting technician seed process...")
    seed_technicians()
