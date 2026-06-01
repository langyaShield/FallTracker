from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import InterviewEvent, Delivery, User
from app.schemas import InterviewEventUpdate, InterviewEventWithDeliveryOut
from app.auth import get_current_user

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=List[InterviewEventWithDeliveryOut])
def list_all_events(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    results = (
        db.query(InterviewEvent, Delivery.company, Delivery.position)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == current_user.id)
        .order_by(InterviewEvent.scheduled_at)
        .all()
    )
    return [
        {
            **{k: getattr(evt, k) for k in InterviewEventWithDeliveryOut.model_fields if hasattr(evt, k)},
            "company": company,
            "position": position,
        }
        for evt, company, position in results
    ]


@router.put("/{event_id}")
def update_event(event_id: int, data: InterviewEventUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = db.query(InterviewEvent).join(Delivery).filter(InterviewEvent.id == event_id, Delivery.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(event, field, value)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    event = db.query(InterviewEvent).join(Delivery).filter(InterviewEvent.id == event_id, Delivery.user_id == current_user.id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    db.delete(event)
    db.commit()
    return {"ok": True}
