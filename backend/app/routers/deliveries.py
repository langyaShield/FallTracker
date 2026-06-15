from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Delivery, InterviewEvent, User
from app.schemas import DeliveryCreate, DeliveryUpdate, DeliveryOut, InterviewEventCreate, InterviewEventUpdate, InterviewEventOut
from app.auth import get_current_user

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get("", response_model=List[DeliveryOut])
def list_deliveries(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Delivery).filter(Delivery.user_id == current_user.id).order_by(Delivery.created_at.desc()).all()


@router.post("", response_model=DeliveryOut)
def create_delivery(data: DeliveryCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_item = Delivery(**data.model_dump(), user_id=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.get("/{delivery_id}", response_model=DeliveryOut)
def get_delivery(delivery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return item


@router.put("/{delivery_id}", response_model=DeliveryOut)
def update_delivery(delivery_id: int, data: DeliveryUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Delivery not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{delivery_id}")
def delete_delivery(delivery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Delivery not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.get("/{delivery_id}/events", response_model=List[InterviewEventOut])
def list_events(delivery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    return db.query(InterviewEvent).filter(InterviewEvent.delivery_id == delivery_id).order_by(InterviewEvent.scheduled_at).all()


@router.post("/{delivery_id}/events", response_model=InterviewEventOut)
def create_event(delivery_id: int, data: InterviewEventCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    db_item = InterviewEvent(**data.model_dump(), delivery_id=delivery_id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
