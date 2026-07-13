from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import ReviewCreate, ReviewUpdate, ReviewOut, ReviewListOut
from app.auth import get_current_user
from app.ratelimit import limiter
from app.modules.reviews.queries import ReviewQueryService
from app.modules.reviews.service import (
    ReviewDeliveryNotFoundError,
    ReviewNotFoundError,
    ReviewService,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=ReviewListOut)
@limiter.limit("60/minute")
def list_reviews(request: Request, limit: int = 0, offset: int = 0, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items, total = ReviewQueryService(db).list_reviews(current_user.id, limit, offset)
    return {"items": items, "total": total}


@router.post("", response_model=ReviewOut)
@limiter.limit("30/minute")
def create_review(request: Request, data: ReviewCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ReviewService(db).create_review(current_user.id, data.model_dump())
    except ReviewDeliveryNotFoundError:
        raise HTTPException(status_code=404, detail="投递不存在")


@router.put("/{review_id}", response_model=ReviewOut)
@limiter.limit("30/minute")
def update_review(review_id: int, request: Request, data: ReviewUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        return ReviewService(db).update_review(review_id, current_user.id, data.model_dump(exclude_unset=True))
    except ReviewNotFoundError:
        raise HTTPException(status_code=404, detail="复盘不存在")


@router.delete("/{review_id}")
@limiter.limit("30/minute")
def delete_review(review_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        ReviewService(db).delete_review(review_id, current_user.id)
    except ReviewNotFoundError:
        raise HTTPException(status_code=404, detail="复盘不存在")
    return {"ok": True}
