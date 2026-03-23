from database import engine
from sqlalchemy import text
import models

models.Base.metadata.create_all(bind=engine)

try:
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE shifts ADD COLUMN max_technicians INTEGER DEFAULT 1"))
        except Exception: pass

        # Postgres enumeration modifications
        try:
            # Need to commit before alter type in PG
            conn.execute(text("COMMIT"))
            conn.execute(text("ALTER TYPE shiftstatus ADD VALUE 'open'"))
        except Exception: pass
        
        try:
            conn.execute(text("COMMIT"))
            conn.execute(text("ALTER TYPE shiftstatus ADD VALUE 'filled'"))
        except Exception: pass

        conn.commit()
        print("Successfully structured new Shift architectures.")
except Exception as e:
    print(f"Error structuring shift bounds: {e}")
