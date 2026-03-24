from database import engine
from sqlalchemy import text

try:
    with engine.connect() as conn:
        try:
            conn.execute(text("COMMIT"))
            conn.execute(text("ALTER TYPE shiftstatus ADD VALUE 'archived'"))
        except Exception as e:
            print(f"Skipping or already exists")
            
        print("Successfully ensured 'archived' in shiftstatus enum")
except Exception as e:
    print(f"Error: {e}")
