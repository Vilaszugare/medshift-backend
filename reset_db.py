from database import engine, Base
import models # Import all models so Base metadata registers them

def reset():
    print("Dropping all tables...")
    # Drops all tables associated with Base
    Base.metadata.drop_all(bind=engine)
    
    print("Recreating all tables with newest schema...")
    # Recreates them with the latest defined models
    Base.metadata.create_all(bind=engine)
    
    print("Database reset successfully!")

if __name__ == "__main__":
    reset()
