from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Delivery, User
from app.auth import get_current_user

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/funnel")
def funnel(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(Delivery.status, func.count(Delivery.id)).filter(Delivery.user_id == current_user.id).group_by(Delivery.status).all()
    data = {"pending": 0, "delivered": 0, "written": 0, "interview": 0, "offer": 0, "rejected": 0}
    for status, count in result:
        if status in data:
            data[status] = count
    return data


@router.get("/conversion")
def conversion(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = db.query(Delivery.status, func.count(Delivery.id)).filter(Delivery.user_id == current_user.id).group_by(Delivery.status).all()
    counts = {"pending": 0, "delivered": 0, "written": 0, "interview": 0, "offer": 0, "rejected": 0}
    for status, count in result:
        if status in counts:
            counts[status] = count
    rates = []
    stages = [("pending", "delivered"), ("delivered", "written"), ("written", "interview"), ("interview", "offer")]
    for a, b in stages:
        if counts[a] > 0:
            rates.append({"stage": f"{a} -> {b}", "rate": round(counts[b] / counts[a] * 100, 1)})
    return rates
