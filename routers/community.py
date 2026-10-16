import os
import uuid
from typing import Optional, List
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
import models

router = APIRouter(prefix="/api", tags=["Community"])

# Directory for uploaded post images
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "posts")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class PostActionRequest(BaseModel):
    user_id: Optional[str] = None


class CommentCreateRequest(BaseModel):
    user_id: str
    content: str
    user_name: Optional[str] = None
    user_role: Optional[str] = None


def to_uuid(val) -> Optional[UUID]:
    if not val:
        return None
    try:
        return UUID(str(val))
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_OID, str(val))


async def save_uploaded_image(file: UploadFile) -> str:
    ext = os.path.splitext(file.filename)[1].lower() if file.filename else ".jpg"
    if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
        ext = ".jpg"
    unique_filename = f"{uuid.uuid4().hex}{ext}"
    destination = os.path.join(UPLOAD_DIR, unique_filename)

    contents = await file.read()
    with open(destination, "wb") as f:
        f.write(contents)

    return f"/uploads/posts/{unique_filename}"


# ── Create Post (Supports multipart/form-data with file upload & JSON) ──────────
@router.post("/posts")
@router.post("/community/posts")
async def create_post(
    request: Request,
    content: Optional[str] = Form(None),
    author_id: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    final_content = content
    final_author_id = author_id
    final_image_url = None

    # Check if request was sent as JSON instead of multipart/form-data
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
            final_content = body.get("content")
            final_author_id = body.get("author_id")
            final_image_url = body.get("image_url")
        except Exception:
            pass

    author_uuid = to_uuid(final_author_id) if final_author_id else uuid.uuid4()

    # If an image file was uploaded via multipart, save it
    if image and image.filename:
        try:
            final_image_url = await save_uploaded_image(image)
        except Exception as e:
            print(f"[Upload Error] Could not save image: {e}")

    # Determine whether author is Manager or Technician
    is_manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == author_uuid).first()

    author_name = "QuickMed Member"
    author_role = "Medical Technician"
    initials = "QM"

    if is_manager:
        author_name = f"{is_manager.first_name} {is_manager.last_name}".strip() or "Hospital Manager"
        hospital = db.query(models.Hospital).filter(models.Hospital.id == is_manager.hospital_id).first() if is_manager.hospital_id else None
        h_name = hospital.name if hospital else "Hospital"
        job = is_manager.job_title or "CMO"
        author_role = f"{job} · {h_name}"
        initials = "".join([n[0] for n in author_name.split() if n])[:2].upper() or "HM"
    else:
        tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == author_uuid).first()
        if tech:
            author_name = tech.full_name or "Medical Technician"
            author_role = tech.title or "Medical Technician"
            initials = "".join([n[0] for n in author_name.split() if n])[:2].upper() or "MT"

    new_post = models.CommunityPost(
        manager_id=author_uuid if is_manager else None,
        technician_id=author_uuid if tech else None,
        content=final_content or "",
        image_url=final_image_url,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return {
        "id": str(new_post.id),
        "author": author_name,
        "initials": initials,
        "role": author_role,
        "content": new_post.content,
        "body": new_post.content,
        "image_url": new_post.image_url,
        "hasImage": bool(new_post.image_url),
        "likes": 0,
        "comments": 0,
        "shares": 0,
        "liked": False,
        "saved": False,
        "created_at": new_post.created_at.isoformat(),
        "time": "Just now",
        "verified": True,
    }


# ── Get Community Posts (Enriched with like/comment counts and user state) ──────
@router.get("/posts")
@router.get("/community/posts")
def get_posts(user_id: Optional[str] = Query(None), db: Session = Depends(get_db)):
    posts = db.query(models.CommunityPost).order_by(models.CommunityPost.created_at.desc()).all()

    user_uuid = to_uuid(user_id) if user_id else None

    result = []
    for post in posts:
        author_name = "QuickMed Member"
        initials = "QM"
        role_label = "Medical Technician"

        if post.manager_id:
            manager = db.query(models.ManagerProfile).filter(models.ManagerProfile.id == post.manager_id).first()
            if manager:
                author_name = f"{manager.first_name} {manager.last_name}".strip() or "Hospital Manager"
                initials = "".join([n[0] for n in author_name.split() if n])[:2].upper() or "HM"
                hospital = db.query(models.Hospital).filter(models.Hospital.id == manager.hospital_id).first() if manager.hospital_id else None
                h_name = hospital.name if hospital else "Hospital"
                role_label = f"{manager.job_title or 'CMO'} · {h_name}"
        elif post.technician_id:
            tech = db.query(models.TechnicianProfile).filter(models.TechnicianProfile.id == post.technician_id).first()
            if tech:
                author_name = tech.full_name or "Technician"
                initials = "".join([n[0] for n in author_name.split() if n])[:2].upper() or "MT"
                role_label = tech.title or "Medical Technician"

        likes_count = db.query(models.PostLike).filter(models.PostLike.post_id == post.id).count()
        comments_count = db.query(models.Comment).filter(models.Comment.post_id == post.id).count()

        is_liked = False
        is_saved = False
        if user_uuid:
            is_liked = db.query(models.PostLike).filter(
                models.PostLike.post_id == post.id,
                models.PostLike.user_id == user_uuid,
            ).first() is not None
            is_saved = db.query(models.SavedPost).filter(
                models.SavedPost.post_id == post.id,
                models.SavedPost.user_id == user_uuid,
            ).first() is not None

        result.append({
            "id": str(post.id),
            "author": author_name,
            "initials": initials,
            "role": role_label,
            "content": post.content,
            "body": post.content,
            "image_url": post.image_url,
            "hasImage": bool(post.image_url),
            "likes": likes_count,
            "comments": comments_count,
            "shares": 0,
            "liked": is_liked,
            "saved": is_saved,
            "created_at": post.created_at.isoformat(),
            "verified": True,
        })

    return result


# ── Toggle Like on Post ────────────────────────────────────────────────────────
@router.post("/posts/{post_id}/like")
@router.post("/community/posts/{post_id}/like")
def toggle_like(
    post_id: UUID,
    payload: Optional[PostActionRequest] = None,
    user_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    target_user_id = (payload.user_id if payload and payload.user_id else None) or user_id
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    user_uuid = to_uuid(target_user_id)

    existing = db.query(models.PostLike).filter(
        models.PostLike.post_id == post_id,
        models.PostLike.user_id == user_uuid,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        liked = False
    else:
        new_like = models.PostLike(post_id=post_id, user_id=user_uuid)
        db.add(new_like)
        db.commit()
        liked = True

    likes_count = db.query(models.PostLike).filter(models.PostLike.post_id == post_id).count()
    return {"status": "success", "liked": liked, "likes": likes_count}


# ── Toggle Save on Post ────────────────────────────────────────────────────────
@router.post("/posts/{post_id}/save")
@router.post("/community/posts/{post_id}/save")
def toggle_save(
    post_id: UUID,
    payload: Optional[PostActionRequest] = None,
    user_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    target_user_id = (payload.user_id if payload and payload.user_id else None) or user_id
    if not target_user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    user_uuid = to_uuid(target_user_id)

    existing = db.query(models.SavedPost).filter(
        models.SavedPost.post_id == post_id,
        models.SavedPost.user_id == user_uuid,
    ).first()

    if existing:
        db.delete(existing)
        db.commit()
        saved = False
    else:
        new_save = models.SavedPost(post_id=post_id, user_id=user_uuid)
        db.add(new_save)
        db.commit()
        saved = True

    return {"status": "success", "saved": saved}


# ── Comments: List & Add ───────────────────────────────────────────────────────
@router.get("/posts/{post_id}/comments")
@router.get("/community/posts/{post_id}/comments")
def get_comments(post_id: UUID, db: Session = Depends(get_db)):
    comments = db.query(models.Comment).filter(
        models.Comment.post_id == post_id
    ).order_by(models.Comment.created_at.asc()).all()

    return [
        {
            "id": str(c.id),
            "post_id": str(c.post_id),
            "user_id": str(c.user_id),
            "user_name": c.user_name or "Member",
            "user_role": c.user_role or "User",
            "content": c.content,
            "created_at": c.created_at.isoformat(),
        }
        for c in comments
    ]


@router.post("/posts/{post_id}/comments")
@router.post("/community/posts/{post_id}/comments")
def add_comment(post_id: UUID, payload: CommentCreateRequest, db: Session = Depends(get_db)):
    user_uuid = to_uuid(payload.user_id)

    new_comment = models.Comment(
        post_id=post_id,
        user_id=user_uuid,
        user_name=payload.user_name or "Member",
        user_role=payload.user_role or "Technician",
        content=payload.content,
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    comments_count = db.query(models.Comment).filter(models.Comment.post_id == post_id).count()

    return {
        "status": "success",
        "comment": {
            "id": str(new_comment.id),
            "post_id": str(new_comment.post_id),
            "user_id": str(new_comment.user_id),
            "user_name": new_comment.user_name,
            "user_role": new_comment.user_role,
            "content": new_comment.content,
            "created_at": new_comment.created_at.isoformat(),
        },
        "comments_count": comments_count,
    }
