"""常用网站：CRUD 操作，支持分类管理。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Bookmark, User
from app.schemas import BookmarkCreate, BookmarkOut, BookmarkUpdate
from app.ratelimit import limiter

router = APIRouter(prefix="/bookmarks", tags=["bookmarks"])


@router.get("", response_model=list[BookmarkOut])
@limiter.limit("60/minute")
def list_bookmarks(
    request: Request,
    limit: int = 0,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户所有网站，按 sort_order 和创建时间排序。支持 limit/offset 分页。"""
    q = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == current_user.id)
        .order_by(Bookmark.sort_order, Bookmark.created_at)
    )
    if limit > 0:
        q = q.limit(limit).offset(offset)
    bookmarks = q.all()
    return [BookmarkOut.model_validate(b) for b in bookmarks]


@router.post("", response_model=BookmarkOut)
@limiter.limit("30/minute")
def create_bookmark(
    request: Request,
    data: BookmarkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新网站。"""
    bookmark = Bookmark(
        user_id=current_user.id,
        title=data.title,
        url=data.url,
        category=data.category,
        icon=data.icon,
        sort_order=data.sort_order,
    )
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return BookmarkOut.model_validate(bookmark)


@router.put("/{bookmark_id}", response_model=BookmarkOut)
@limiter.limit("30/minute")
def update_bookmark(
    bookmark_id: int,
    request: Request,
    data: BookmarkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新网站。"""
    bookmark = (
        db.query(Bookmark)
        .filter(Bookmark.id == bookmark_id, Bookmark.user_id == current_user.id)
        .first()
    )
    if not bookmark:
        raise HTTPException(status_code=404, detail="网站不存在")
    for field_name, value in data.model_dump(exclude_unset=True).items():
        setattr(bookmark, field_name, value)
    db.commit()
    db.refresh(bookmark)
    return BookmarkOut.model_validate(bookmark)


@router.delete("/{bookmark_id}")
@limiter.limit("30/minute")
def delete_bookmark(
    bookmark_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除网站。"""
    bookmark = (
        db.query(Bookmark)
        .filter(Bookmark.id == bookmark_id, Bookmark.user_id == current_user.id)
        .first()
    )
    if not bookmark:
        raise HTTPException(status_code=404, detail="网站不存在")
    db.delete(bookmark)
    db.commit()
    return {"success": True, "message": f"已删除网站 {bookmark.title}"}
