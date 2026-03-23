from pydantic import BaseModel, ConfigDict
from typing import List, Optional
from datetime import datetime
from uuid import UUID

# ==========================================
# POST SCHEMA DEFINITIONS
# ==========================================
class AvailabilityUpdate(BaseModel):
    is_available: bool

class ShiftApplySchema(BaseModel):
    technician_id: UUID

class TechnicianRegisterRequest(BaseModel):
    full_name: str
    mobile_number: str
    email: str
    password: str
    id_document: Optional[str] = None
    certificate: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str
    role: str

class ShiftCreate(BaseModel):
    manager_id: UUID
    title: str
    department: Optional[str] = "General"
    start_time: datetime
    end_time: Optional[datetime] = None
    hourly_rate: float
    is_urgent: bool = False

class CommunityPostCreate(BaseModel):
    author_id: UUID
    content: str
    image_url: Optional[str] = None

# ==========================================
# SHARED SCHEMAS
# ==========================================
class ShiftApplicantSchema(BaseModel):
    id: UUID
    technician_id: UUID
    name: str
    rating: float
    status: str
    applied_at: datetime

class ShiftBase(BaseModel):
    id: UUID
    title: str
    department: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]
    hourly_rate: float
    status: str
    is_urgent: bool
    duration: float
    technician_id: Optional[UUID] = None
    technician_name: Optional[str] = None
    technician_phone: Optional[str] = None
    max_technicians: int = 1
    pending_count: int = 0
    accepted_count: int = 0
    accepted_technicians: List[ShiftApplicantSchema] = []

    model_config = ConfigDict(from_attributes=True)

class CommunityPostBase(BaseModel):
    id: UUID
    manager_id: Optional[UUID] = None
    technician_id: Optional[UUID] = None
    content: str
    image_url: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

# ==========================================
# MANAGER DASHBOARD SCHEMAS
# ==========================================
class ManagerProfileSchema(BaseModel):
    name: str
    role: str
    hospital_name: str
    hospital_area: str
    is_verified: bool

class ManagerProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    mobile_number: Optional[str] = None
    job_title: Optional[str] = None
    hospital_name: Optional[str] = None
    hospital_address: Optional[str] = None
    facilities: Optional[str] = None
    certifications: Optional[str] = None

class ManagerStatsSchema(BaseModel):
    active_shifts: int
    historical_hires: int
    hospital_rating: float

class ManagerDashboardResponse(BaseModel):
    profile: ManagerProfileSchema
    stats: ManagerStatsSchema
    posted_shifts: List[ShiftBase]

# ==========================================
# TECHNICIAN DASHBOARD SCHEMAS
# ==========================================
class TechProfileSchema(BaseModel):
    name: str
    title: str
    location: str
    rating: float
    total_shifts: int
    is_available: bool

class TechnicianProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    mobile_number: Optional[str] = None
    bio: Optional[str] = None
    specialty: Optional[str] = None
    machine_skills: Optional[str] = None
    certifications_list: Optional[str] = None
    experience_years: Optional[int] = None
    country: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    city: Optional[str] = None
    home_address: Optional[str] = None

class TechStatsSchema(BaseModel):
    total_earnings: float
    completed_shifts: int

class TechShiftSchema(ShiftBase):
    hospital_name: str

class TechDashboardResponse(BaseModel):
    profile: TechProfileSchema
    stats: TechStatsSchema
    nearby_shifts: List[TechShiftSchema]
