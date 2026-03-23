from database import engine
from sqlalchemy import text

cols = [
    "bio TEXT",
    "specialty VARCHAR(200)",
    "machine_skills VARCHAR(500)",
    "certifications_list VARCHAR(500)",
    "experience_years INTEGER",
    "country VARCHAR(100)",
    "state VARCHAR(100)",
    "district VARCHAR(100)",
    "city VARCHAR(100)",
    "home_address TEXT"
]

try:
    with engine.connect() as conn:
        for col in cols:
            try:
                conn.execute(text(f"ALTER TABLE technician_profiles ADD COLUMN {col}"))
            except Exception as e:
                pass
        conn.commit()
        print("Added tech profile columns")
except Exception as e:
    print(e)
