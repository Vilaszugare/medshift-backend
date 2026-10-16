import enum
import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, DateTime, Enum, Text, UUID
from sqlalchemy.orm import relationship
from database import Base


class ShiftStatus(str, enum.Enum):
    searching = "searching"
    matched = "matched"
    open = "open"
    filled = "filled"
    completed = "completed"
    cancelled = "cancelled"
    archived = "archived"

class ShiftAssignmentStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    withdrawn = "withdrawn"
    rejected = "rejected"

class TransactionType(str, enum.Enum):
    credit = "credit"
    debit = "debit"
    payout = "payout"

class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)



class Hospital(Base, TimestampMixin):
    __tablename__ = "hospitals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(255), nullable=False, index=True)
    address = Column(Text, nullable=False)
    latitude = Column(Float, index=True)
    longitude = Column(Float, index=True)
    is_verified = Column(Boolean, default=False)
    facilities = Column(String(500), nullable=True)
    certifications = Column(String(500), nullable=True)
    
    managers = relationship("ManagerProfile", back_populates="hospital")

class ManagerProfile(Base, TimestampMixin):
    __tablename__ = "manager_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    hospital_id = Column(UUID(as_uuid=True), ForeignKey("hospitals.id", ondelete="RESTRICT"), nullable=False)
    
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    job_title = Column(String(100))
    mobile_number = Column(String(20), nullable=True)
    fcm_token = Column(String(500), nullable=True)
    
    hospital = relationship("Hospital", back_populates="managers")
    shifts = relationship("Shift", back_populates="manager_user")

class TechnicianProfile(Base, TimestampMixin):
    __tablename__ = "technician_profiles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    full_name = Column(String(200), nullable=False)
    title = Column(String(100))
    
    mobile_number = Column(String(20), unique=True, index=True)
    id_document_url = Column(String(500), nullable=True)
    certificate_url = Column(String(500), nullable=True)
    verification_status = Column(String(50), default="pending")
    fcm_token = Column(String(500), nullable=True)
    
    is_available = Column(Boolean, default=True, index=True)
    rating = Column(Float, default=0.0)
    total_shifts = Column(Integer, default=0)
    
    latitude = Column(Float, index=True)
    longitude = Column(Float, index=True)
    
    bio = Column(Text, nullable=True)
    specialty = Column(String(200), nullable=True)
    machine_skills = Column(String(500), nullable=True)
    certifications_list = Column(String(500), nullable=True)
    experience_years = Column(Integer, nullable=True)
    country = Column(String(100), nullable=True)
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    home_address = Column(Text, nullable=True)
    
    shifts = relationship("Shift", back_populates="technician")

class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("manager_profiles.id", ondelete="RESTRICT"), nullable=False)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technician_profiles.id", ondelete="SET NULL"), nullable=True)
    
    title = Column(String(255), nullable=False)
    department = Column(String(100), nullable=True, default="General")
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True) 
    hourly_rate = Column(Float, nullable=False)
    is_urgent = Column(Boolean, default=False, index=True)
    status = Column(Enum(ShiftStatus), default=ShiftStatus.open, nullable=False, index=True)
    max_technicians = Column(Integer, default=1)
    
    manager_user = relationship("ManagerProfile", back_populates="shifts", foreign_keys=[manager_id])
    technician = relationship("TechnicianProfile", back_populates="shifts")
    assignments = relationship("ShiftAssignment", back_populates="shift", cascade="all, delete-orphan")

class ShiftAssignment(Base, TimestampMixin):
    __tablename__ = "shift_assignments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    shift_id = Column(UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technician_profiles.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(ShiftAssignmentStatus), default=ShiftAssignmentStatus.pending, nullable=False, index=True)
    accepted_at = Column(DateTime, nullable=True)

    shift = relationship("Shift", back_populates="assignments")
    technician = relationship("TechnicianProfile", foreign_keys=[technician_id])

class CommunityPost(Base, TimestampMixin):
    __tablename__ = "community_posts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("manager_profiles.id", ondelete="CASCADE"), nullable=True)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technician_profiles.id", ondelete="CASCADE"), nullable=True)
    content = Column(Text, nullable=False)
    image_url = Column(String(500), nullable=True)
    
    manager = relationship("ManagerProfile")
    technician = relationship("TechnicianProfile")
    likes = relationship("PostLike", back_populates="post", cascade="all, delete-orphan")
    saved_by = relationship("SavedPost", back_populates="post", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan", order_by="Comment.created_at.asc()")

# Post alias for CommunityPost
Post = CommunityPost


class PostLike(Base):
    __tablename__ = "post_likes"
    # Composite primary key consisting of post_id and user_id to enforce uniqueness
    post_id = Column(UUID(as_uuid=True), ForeignKey("community_posts.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("CommunityPost", back_populates="likes")


class SavedPost(Base):
    __tablename__ = "saved_posts"
    # Composite primary key consisting of post_id and user_id to enforce uniqueness
    post_id = Column(UUID(as_uuid=True), ForeignKey("community_posts.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(UUID(as_uuid=True), primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("CommunityPost", back_populates="saved_by")


class Comment(Base):
    __tablename__ = "post_comments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    post_id = Column(UUID(as_uuid=True), ForeignKey("community_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_name = Column(String(255), nullable=True)
    user_role = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    post = relationship("CommunityPost", back_populates="comments")

class IndianState(Base, TimestampMixin):
    __tablename__ = "indian_states"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String(100), unique=True, index=True)

class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("manager_profiles.id", ondelete="RESTRICT"), nullable=True)
    technician_id = Column(UUID(as_uuid=True), ForeignKey("technician_profiles.id", ondelete="RESTRICT"), nullable=True)
    shift_id = Column(UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True) 
    type = Column(Enum(TransactionType), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    status = Column(String(50), default="pending", index=True)
    
    manager = relationship("ManagerProfile")
    technician = relationship("TechnicianProfile")


class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)  # Unified recipient ID
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    icon = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    is_read = Column(Boolean, default=False)

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    shift_id = Column(UUID(as_uuid=True), ForeignKey("shifts.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    receiver_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    shift = relationship("Shift")

class SuggestedReply(Base):
    __tablename__ = "suggested_replies"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    role = Column(String(50), nullable=False, index=True)   # e.g. "manager"
    content = Column(String(500), nullable=False)

