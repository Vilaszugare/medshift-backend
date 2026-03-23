from database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE manager_profiles ADD COLUMN mobile_number VARCHAR(20)"))
        conn.commit()
        print("Added mobile_number")
except Exception as e:
    print(e)
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE hospitals ADD COLUMN facilities VARCHAR(500)"))
        conn.commit()
        print("Added facilities")
except Exception as e:
    print(e)
try:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE hospitals ADD COLUMN certifications VARCHAR(500)"))
        conn.commit()
        print("Added certifications")
except Exception as e:
    print(e)
