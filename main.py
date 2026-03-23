# Entry point of the application
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import get_db
import models
from fastapi.middleware.cors import CORSMiddleware
from routers import manager_dashboard, manager_actions, auth, technician_actions

app = FastAPI(title="MedShift API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "https://medmis.vercel.app",
        "https://lics-fry.loca.lt",
        "capacitor://localhost",
        "http://localhost",
        "https://localhost"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(manager_dashboard.router)
app.include_router(manager_actions.router)
app.include_router(technician_actions.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the MedShift API"}

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Backend is awake"}

@app.get("/api/states")
def get_indian_states(db: Session = Depends(get_db)):
    states = db.query(models.IndianState).order_by(models.IndianState.name).all()
    return {"states": [s.name for s in states]}
