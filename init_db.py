from database import engine, Base
import models

def init_db():
    print("Connecting to the database...")
    print("Creating tables if they do not exist...")
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully!")

if __name__ == "__main__":
    init_db()
