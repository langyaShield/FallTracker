"""常用网站：CRUD 操作，支持分类管理。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas import BookmarkCreate, BookmarkOut, BookmarkUpdate
from app.ratelimit import limiter
from app.modules.bookmarks.queries import BookmarkQueryService
from app.modules.bookmarks.service import BookmarkNotFoundError, BookmarkService

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
    bookmarks = BookmarkQueryService(db).list_bookmarks(current_user.id, limit, offset)
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
    bookmark = BookmarkService(db).create_bookmark(current_user.id, data.model_dump())
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
    try:
        bookmark = BookmarkService(db).update_bookmark(
            bookmark_id, current_user.id, data.model_dump(exclude_unset=True)
        )
    except BookmarkNotFoundError:
        raise HTTPException(status_code=404, detail="网站不存在")
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
    try:
        bookmark = BookmarkService(db).delete_bookmark(bookmark_id, current_user.id)
    except BookmarkNotFoundError:
        raise HTTPException(status_code=404, detail="网站不存在")
    return {"success": True, "message": f"已删除网站 {bookmark.title}"}
