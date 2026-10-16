import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

# Securely grab the connection string
DATABASE_URL = os.getenv("DATABASE_URL")

# SQLAlchemy requires the URL to start with postgresql:// or postgresql+psycopg2://
# Many hosted services (like Supabase) hand out 'postgres://' URIs.
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Initialize the SQLAlchemy Engine
# pool_pre_ping=True checks the connection before pooling to prevent stale connection errors
from sqlalchemy.pool import NullPool
connect_args = {}
poolclass = None

if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif DATABASE_URL and "6543" in DATABASE_URL:
    connect_args = {"client_encoding": "utf8", "prepare_threshold": None}
    poolclass = NullPool

if poolclass:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, poolclass=poolclass)
else:
    engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)

# SessionLocal is the factory for new Session objects (database connections)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for declarative class definitions (used by models.py)
Base = declarative_base()

# FastAPI Dependency for injecting the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
