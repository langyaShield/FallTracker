from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Review, Delivery, User
from app.schemas import ReviewCreate, ReviewUpdate, ReviewOut, ReviewListOut
from app.auth import get_current_user
from app.ratelimit import limiter

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=ReviewListOut)
@limiter.limit("60/minute")
def list_reviews(request: Request, limit: int = 0, offset: int = 0, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = db.query(Review).filter(Review.user_id == current_user.id)
    total = q.count()
    q = q.order_by(Review.created_at.desc())
    if limit > 0:
        q = q.limit(limit).offset(offset)
    return {"items": q.all(), "total": total}


@router.post("", response_model=ReviewOut)
@limiter.limit("30/minute")
def create_review(request: Request, data: ReviewCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == data.delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="投递不存在")
    db_item = Review(**data.model_dump(), user_id=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/{review_id}", response_model=ReviewOut)
@limiter.limit("30/minute")
def update_review(review_id: int, request: Request, data: ReviewUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="复盘不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{review_id}")
@limiter.limit("30/minute")
def delete_review(review_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="复盘不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}
