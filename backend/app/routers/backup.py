"""
数据备份：全量导出 / 导入 + 腾讯云 COS 云端备份

导出当前用户所有业务数据为 JSON 文件，导入时按依赖顺序重建记录并重映射 ID。
支持上传到腾讯云 COS 和从 COS 恢复。
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.crypto import decrypt_value
from app.database import get_db, SessionLocal
from app.ratelimit import limiter
from app.models import (
    Bookmark,
    CrawlerConfig,
    CrawlerResult,
    Delivery,
    DeliveryNote,
    InterviewEvent,
    Notification,
    ProfileField,
    Resume,
    Review,
    User,
    UserSettings,
)

logger = logging.getLogger("falltracker")

router = APIRouter(prefix="/backup", tags=["backup"])

BACKUP_VERSION = "1.0"

# 序列化时排除的字段（内部 ID、敏感字段、自动管理的时间戳）
_EXCLUDE_FIELDS = {"id", "user_id", "password_hash", "updated_at"}

# 导入时跳过自动管理的字段（由数据库 server_default/onupdate 处理）
_IMPORT_SKIP_FIELDS = {"updated_at"}


# ═══════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════


def _model_to_dict(obj, extra_exclude: Optional[set] = None) -> dict:
    """将 SQLAlchemy 模型实例转为字典，排除内部字段。"""
    exclude = _EXCLUDE_FIELDS | (extra_exclude or set())
    result = {}
    for col in obj.__table__.columns:
        if col.name in exclude:
            continue
        val = getattr(obj, col.name)
        if val is not None and hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col.name] = val
    return result


def _parse_datetime(val):
    """尝试解析日期时间字符串。"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(val) if "T" in str(val) else datetime.strptime(val, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _prepare_item(item: dict, model_class, skip_fields: set = None) -> dict:
    """Prepare a dict item for SQLAlchemy model creation: convert datetime strings
    and strip fields that should not be set directly (auto-managed, internal IDs)."""
    skip = (_IMPORT_SKIP_FIELDS | (skip_fields or set()))
    table_cols = model_class.__table__.columns
    result = {}
    for k, v in item.items():
        if k in skip:
            continue
        if k not in table_cols:
            continue
        col = table_cols[k]
        if col.type.__class__.__name__ in ("DateTime", "Date", "DATETIME", "DATE", "Timestamp"):
            v = _parse_datetime(v)
        result[k] = v
    return result


# ═══════════════════════════════════════════════════════════════
#  Data gathering (shared by export & COS upload)
# ═══════════════════════════════════════════════════════════════


def _gather_backup_data(db: Session, uid: int) -> dict:
    """Collect all user data into a dict ready for JSON serialization."""

    # UserSettings
    settings = db.query(UserSettings).filter(UserSettings.user_id == uid).first()
    user_settings = _model_to_dict(settings) if settings else {}

    # CrawlerConfig
    configs = db.query(CrawlerConfig).filter(CrawlerConfig.user_id == uid).all()
    crawler_configs = []
    for c in configs:
        d = _model_to_dict(c)
        d["_old_id"] = c.id
        crawler_configs.append(d)

    # CrawlerResult
    results = db.query(CrawlerResult).join(
        CrawlerConfig, CrawlerResult.config_id == CrawlerConfig.id
    ).filter(CrawlerConfig.user_id == uid).all()
    crawler_results = []
    for r in results:
        d = _model_to_dict(r)
        d["_old_config_id"] = r.config_id
        d.pop("config_id", None)
        crawler_results.append(d)

    # Resume
    resumes = db.query(Resume).filter(Resume.user_id == uid).all()
    resume_list = []
    for r in resumes:
        d = _model_to_dict(r)
        d["_old_id"] = r.id
        resume_list.append(d)

    # Delivery
    deliveries = db.query(Delivery).filter(Delivery.user_id == uid).all()
    delivery_list = []
    for d in deliveries:
        dd = _model_to_dict(d)
        dd["_old_id"] = d.id
        if d.resume_id is not None:
            dd["_old_resume_id"] = d.resume_id
            dd.pop("resume_id", None)
        delivery_list.append(dd)

    # InterviewEvent — deduplicate by (event_type, scheduled_at, _old_delivery_id)
    events = (
        db.query(InterviewEvent)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == uid)
        .all()
    )
    seen_events = set()
    event_list = []
    for e in events:
        d = _model_to_dict(e)
        d["_old_delivery_id"] = e.delivery_id
        d.pop("delivery_id", None)
        # Dedup key: same delivery + same event type + same round + same scheduled time
        dedup_key = (e.delivery_id, d.get("event_type"), d.get("round_number"), d.get("scheduled_at"))
        if dedup_key in seen_events:
            continue
        seen_events.add(dedup_key)
        event_list.append(d)

    # Review
    reviews = (
        db.query(Review)
        .join(Delivery, Review.delivery_id == Delivery.id)
        .filter(Delivery.user_id == uid)
        .all()
    )
    review_list = []
    for r in reviews:
        d = _model_to_dict(r)
        d["_old_delivery_id"] = r.delivery_id
        d.pop("delivery_id", None)
        review_list.append(d)

    # Notification
    notifications = db.query(Notification).filter(Notification.user_id == uid).all()
    notification_list = [_model_to_dict(n) for n in notifications]

    # ProfileField
    profile_fields = db.query(ProfileField).filter(ProfileField.user_id == uid).all()
    profile_field_list = [_model_to_dict(pf) for pf in profile_fields]

    # Bookmark
    bookmarks = db.query(Bookmark).filter(Bookmark.user_id == uid).all()
    bookmark_list = [_model_to_dict(b) for b in bookmarks]

    # DeliveryNote
    notes = (
        db.query(DeliveryNote)
        .join(Delivery, DeliveryNote.delivery_id == Delivery.id)
        .filter(Delivery.user_id == uid)
        .all()
    )
    note_list = []
    for n in notes:
        d = _model_to_dict(n)
        d["_old_delivery_id"] = n.delivery_id
        d.pop("delivery_id", None)
        note_list.append(d)

    return {
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_settings": user_settings,
        "crawler_configs": crawler_configs,
        "crawler_results": crawler_results,
        "resumes": resume_list,
        "deliveries": delivery_list,
        "interview_events": event_list,
        "reviews": review_list,
        "notifications": notification_list,
        "profile_fields": profile_field_list,
        "bookmarks": bookmark_list,
        "delivery_notes": note_list,
    }


# ═══════════════════════════════════════════════════════════════
#  Data import (shared by local import & COS restore)
# ═══════════════════════════════════════════════════════════════


def _import_backup_data(db: Session, uid: int, data: dict) -> dict:
    """Import backup data for a user. Overwrites all existing data first.
    Returns stats dict with counts per entity type."""

    stats = {}

    # ── Overwrite: delete all existing user data ──
    delivery_ids = [row[0] for row in db.query(Delivery.id).filter(Delivery.user_id == uid).all()]
    config_ids = [row[0] for row in db.query(CrawlerConfig.id).filter(CrawlerConfig.user_id == uid).all()]

    db.query(Bookmark).filter(Bookmark.user_id == uid).delete()
    db.query(ProfileField).filter(ProfileField.user_id == uid).delete()
    db.query(Notification).filter(Notification.user_id == uid).delete()
    db.query(Review).filter(Review.user_id == uid).delete()
    if delivery_ids:
        db.query(DeliveryNote).filter(
            DeliveryNote.delivery_id.in_(delivery_ids)
        ).delete(synchronize_session=False)
        db.query(InterviewEvent).filter(
            InterviewEvent.delivery_id.in_(delivery_ids)
        ).delete(synchronize_session=False)
    db.query(Delivery).filter(Delivery.user_id == uid).delete()
    if config_ids:
        db.query(CrawlerResult).filter(
            CrawlerResult.config_id.in_(config_ids)
        ).delete(synchronize_session=False)
    db.query(CrawlerConfig).filter(CrawlerConfig.user_id == uid).delete()
    db.query(Resume).filter(Resume.user_id == uid).delete()
    db.query(UserSettings).filter(UserSettings.user_id == uid).delete()
    db.commit()

    # ── 1. UserSettings ──
    settings_data = data.get("user_settings", {})
    if settings_data:
        prepared = _prepare_item(settings_data, UserSettings)
        prepared["user_id"] = uid
        existing = UserSettings(**prepared)
        db.add(existing)
        db.flush()
    stats["user_settings"] = 1 if settings_data else 0

    # ── 2. CrawlerConfig ──
    config_id_map = {}
    for item in data.get("crawler_configs", []):
        old_id = item.pop("_old_id", None)
        prepared = _prepare_item(item, CrawlerConfig)
        obj = CrawlerConfig(user_id=uid, **prepared)
        db.add(obj)
        db.flush()
        if old_id is not None:
            config_id_map[old_id] = obj.id
    stats["crawler_configs"] = len(data.get("crawler_configs", []))

    # ── 3. CrawlerResult ──
    for item in data.get("crawler_results", []):
        old_config_id = item.pop("_old_config_id", None)
        new_config_id = config_id_map.get(old_config_id)
        if new_config_id is None:
            continue
        prepared = _prepare_item(item, CrawlerResult)
        obj = CrawlerResult(config_id=new_config_id, **prepared)
        db.add(obj)
    db.flush()
    stats["crawler_results"] = len(data.get("crawler_results", []))

    # ── 4. Resume ──
    resume_id_map = {}
    for item in data.get("resumes", []):
        old_id = item.pop("_old_id", None)
        prepared = _prepare_item(item, Resume)
        obj = Resume(user_id=uid, **prepared)
        db.add(obj)
        db.flush()
        if old_id is not None:
            resume_id_map[old_id] = obj.id
    stats["resumes"] = len(data.get("resumes", []))

    # ── 5. Delivery ──
    delivery_id_map = {}
    for item in data.get("deliveries", []):
        old_id = item.pop("_old_id", None)
        old_resume_id = item.pop("_old_resume_id", None)
        if old_resume_id is not None and old_resume_id in resume_id_map:
            item["resume_id"] = resume_id_map[old_resume_id]
        prepared = _prepare_item(item, Delivery)
        obj = Delivery(user_id=uid, **prepared)
        db.add(obj)
        db.flush()
        if old_id is not None:
            delivery_id_map[old_id] = obj.id
    stats["deliveries"] = len(data.get("deliveries", []))

    # ── 6. InterviewEvent ──
    for item in data.get("interview_events", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        prepared = _prepare_item(item, InterviewEvent)
        obj = InterviewEvent(delivery_id=new_delivery_id, **prepared)
        db.add(obj)
    db.flush()
    stats["interview_events"] = len(data.get("interview_events", []))

    # ── 7. Review ──
    for item in data.get("reviews", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        prepared = _prepare_item(item, Review)
        obj = Review(user_id=uid, delivery_id=new_delivery_id, **prepared)
        db.add(obj)
    db.flush()
    stats["reviews"] = len(data.get("reviews", []))

    # ── 8. Notification ──
    for item in data.get("notifications", []):
        prepared = _prepare_item(item, Notification)
        obj = Notification(user_id=uid, **prepared)
        db.add(obj)
    db.flush()
    stats["notifications"] = len(data.get("notifications", []))

    # ── 9. ProfileField ──
    for item in data.get("profile_fields", []):
        prepared = _prepare_item(item, ProfileField)
        obj = ProfileField(user_id=uid, **prepared)
        db.add(obj)
    db.flush()
    stats["profile_fields"] = len(data.get("profile_fields", []))

    # ── 10. Bookmark ──
    for item in data.get("bookmarks", []):
        prepared = _prepare_item(item, Bookmark)
        obj = Bookmark(user_id=uid, **prepared)
        db.add(obj)
    db.flush()
    stats["bookmarks"] = len(data.get("bookmarks", []))

    # ── 11. DeliveryNote ──
    for item in data.get("delivery_notes", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        prepared = _prepare_item(item, DeliveryNote)
        obj = DeliveryNote(user_id=uid, delivery_id=new_delivery_id, **prepared)
        db.add(obj)
    db.flush()
    stats["delivery_notes"] = len(data.get("delivery_notes", []))

    db.commit()
    return stats


# ═══════════════════════════════════════════════════════════════
#  Export
# ═══════════════════════════════════════════════════════════════


@router.get("/export")
def export_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出当前用户全量数据为 JSON 文件。"""
    data = _gather_backup_data(db, current_user.id)
    buf = BytesIO()
    buf.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    filename = f"falltracker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══════════════════════════════════════════════════════════════
#  Import
# ═══════════════════════════════════════════════════════════════


MAX_IMPORT_SIZE = 50 * 1024 * 1024  # 50MB


@limiter.limit("3/minute")
@router.post("/import")
def import_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导入 JSON 备份文件恢复数据（覆盖模式：先清空再导入）。"""
    # Security: limit upload size to prevent DoS
    chunks = []
    total_size = 0
    while True:
        chunk = file.file.read(8192)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > MAX_IMPORT_SIZE:
            raise HTTPException(status_code=413, detail="备份文件过大，不能超过 50MB")
        chunks.append(chunk)
    content = b"".join(chunks)

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"无效的 JSON 文件: {e}")

    if "version" not in data:
        raise HTTPException(status_code=400, detail="无效的备份文件：缺少 version 字段")

    stats = _import_backup_data(db, current_user.id, data)
    return {"imported": stats}


# ═══════════════════════════════════════════════════════════════
#  COS Cloud Backup
# ═══════════════════════════════════════════════════════════════


def _get_cos_client(s: UserSettings):
    """从用户设置构建 COS 客户端，未配置时抛出 HTTPException。"""
    secret_id = decrypt_value(s.cos_secret_id)
    secret_key = decrypt_value(s.cos_secret_key)
    bucket = s.cos_bucket
    region = s.cos_region
    if not all([secret_id, secret_key, bucket, region]):
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")
    try:
        from qcloud_cos import CosConfig, CosS3Client
        config = CosConfig(Region=region, SecretId=secret_id, SecretKey=secret_key)
        return CosS3Client(config), bucket, region
    except ImportError:
        raise HTTPException(status_code=500, detail="COS SDK 未安装，请安装 cos-python-sdk-v5")
    except Exception as e:
        logger.error("COS config error: %s", e)
        raise HTTPException(status_code=400, detail="COS 配置有误，请检查参数设置")


@limiter.limit("3/minute")
@router.post("/upload-to-cos")
def upload_to_cos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将全量数据导出并上传到腾讯云 COS（手动备份）。"""
    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    client, bucket, region = _get_cos_client(s)
    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"

    data = _gather_backup_data(db, current_user.id)
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_key = f"{path_prefix}falltracker_manual_{timestamp}.json"

    logger.info("COS upload (manual): key=%s, size=%d", file_key, len(content))

    try:
        client.put_object(
            Bucket=bucket,
            Key=file_key,
            Body=content,
            ContentType="application/json",
        )
    except Exception as e:
        logger.error("COS upload failed: key=%s, error=%s", file_key, e)
        raise HTTPException(status_code=500, detail="上传到 COS 失败，请检查网络和 COS 配置")

    return {
        "success": True,
        "file_key": file_key,
        "size": len(content),
        "message": f"已上传到 COS: {file_key}",
    }


@router.get("/cos-list")
def list_cos_backups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出 COS 上的备份文件。"""
    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    client, bucket, region = _get_cos_client(s)
    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"

    try:
        resp = client.list_objects(Bucket=bucket, Prefix=path_prefix)
    except Exception as e:
        logger.error("COS list failed: %s", e)
        raise HTTPException(status_code=500, detail="获取 COS 文件列表失败，请检查网络和 COS 配置")

    files = []
    for obj in resp.get("Contents", []):
        files.append({
            "key": obj["Key"],
            "size": obj["Size"],
            "last_modified": obj["LastModified"],
        })
    files.sort(key=lambda x: x["last_modified"], reverse=True)
    return files


@router.post("/cos-delete")
def delete_cos_backup(
    file_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 COS 上的指定备份文件。"""
    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    client, bucket, region = _get_cos_client(s)
    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"

    if not file_key.startswith(path_prefix):
        raise HTTPException(status_code=403, detail="只能删除备份目录下的文件")

    try:
        client.delete_object(Bucket=bucket, Key=file_key)
        logger.info("COS delete: key=%s", file_key)
    except Exception as e:
        logger.error("COS delete failed: key=%s, error=%s", file_key, e)
        raise HTTPException(status_code=500, detail="删除 COS 文件失败，请检查网络和 COS 配置")

    return {"success": True, "file_key": file_key, "message": "备份已删除"}


@router.post("/cos-rename")
def rename_cos_backup(
    file_key: str = Form(...),
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重命名 COS 上的备份文件（通过拷贝+删除实现）。"""
    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    client, bucket, region = _get_cos_client(s)
    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"

    if not file_key.startswith(path_prefix):
        raise HTTPException(status_code=403, detail="只能操作备份目录下的文件")

    dir_part = file_key.rsplit("/", 1)[0] + "/" if "/" in file_key else path_prefix
    new_key = dir_part + new_name
    if not new_key.endswith(".json"):
        new_key += ".json"

    try:
        copy_source = {"Bucket": bucket, "Key": file_key, "Region": region}
        client.copy_object(
            Bucket=bucket,
            Key=new_key,
            CopySource=copy_source,
        )
        client.delete_object(Bucket=bucket, Key=file_key)
        logger.info("COS rename: %s -> %s", file_key, new_key)
    except Exception as e:
        logger.error("COS rename failed: key=%s, error=%s", file_key, e)
        raise HTTPException(status_code=500, detail="重命名 COS 文件失败，请检查网络和 COS 配置")

    return {"success": True, "old_key": file_key, "new_key": new_key, "message": "备份已重命名"}


@limiter.limit("3/minute")
@router.post("/restore-from-cos")
def restore_from_cos(
    file_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从 COS 下载备份文件并导入恢复数据（覆盖模式：先清空再导入）。"""
    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    # Security: validate file_key is within the user's backup path prefix
    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"
    if not file_key.startswith(path_prefix):
        raise HTTPException(status_code=403, detail="无权访问该备份文件")

    client, bucket, region = _get_cos_client(s)

    try:
        resp = client.get_object(Bucket=bucket, Key=file_key)
        body = resp["Body"]
        chunks = []
        while True:
            chunk = body.read(8192)
            if not chunk:
                break
            chunks.append(chunk)
        content = b"".join(chunks)
        logger.info(
            "COS download: key=%s, expected_size=%s, actual_size=%d",
            file_key,
            resp.get("Content-Length", "unknown"),
            len(content),
        )
    except Exception as e:
        logger.error("COS download failed: key=%s, error=%s", file_key, e)
        raise HTTPException(status_code=500, detail="从 COS 下载备份文件失败，请检查 COS 配置")

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("JSON parse failed: %s, first 200 bytes: %r", e, content[:200])
        raise HTTPException(status_code=400, detail=f"无效的 JSON 文件: {e}")

    if "version" not in data:
        raise HTTPException(status_code=400, detail="无效的备份文件：缺少 version 字段")

    stats = _import_backup_data(db, current_user.id, data)
    return {"source": "cos", "file_key": file_key, "imported": stats}


# ═══════════════════════════════════════════════════════════════
#  Auto Backup (called by APScheduler)
# ═══════════════════════════════════════════════════════════════


def auto_backup_all_users() -> None:
    """Scan all users with cos_auto_backup_hours configured and run auto-backup
    for those whose last auto-backup is older than the configured interval.

    Called periodically by APScheduler.
    """
    db = SessionLocal()
    try:
        users_with_auto = (
            db.query(UserSettings)
            .filter(UserSettings.cos_auto_backup_hours.isnot(None))
            .filter(UserSettings.cos_auto_backup_hours > 0)
            .all()
        )
        for s in users_with_auto:
            try:
                _auto_backup_user(db, s)
            except Exception as e:
                logger.error("Auto backup failed for user_id=%s: %s", s.user_id, e)
    except Exception as e:
        logger.exception("auto_backup_all_users failed: %s", e)
    finally:
        db.close()


def _auto_backup_user(db: Session, s: UserSettings) -> None:
    """Perform auto-backup for a single user if the interval has elapsed."""
    from app.models import User as UserModel

    # Verify user exists and is not disabled
    user = db.query(UserModel).filter(UserModel.id == s.user_id, UserModel.is_disabled.is_(False)).first()
    if not user:
        return

    # Check COS config is complete
    secret_id = decrypt_value(s.cos_secret_id)
    secret_key = decrypt_value(s.cos_secret_key)
    if not all([secret_id, secret_key, s.cos_bucket, s.cos_region]):
        logger.debug("Skipping auto-backup for user_id=%s: COS not configured", s.user_id)
        return

    # Check if enough time has elapsed since last auto-backup
    # We check the latest auto backup file on COS by listing with prefix
    interval_hours = s.cos_auto_backup_hours or 0
    if interval_hours <= 0:
        return

    try:
        from qcloud_cos import CosConfig, CosS3Client
        config = CosConfig(Region=s.cos_region, SecretId=secret_id, SecretKey=secret_key)
        client = CosS3Client(config)
    except Exception as e:
        logger.error("COS client init failed for user_id=%s: %s", s.user_id, e)
        return

    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"
    auto_prefix = f"{path_prefix}falltracker_auto_"

    # List existing auto-backup files to find the most recent one
    try:
        resp = client.list_objects(Bucket=s.cos_bucket, Prefix=auto_prefix)
        contents = resp.get("Contents", [])
        if contents:
            # Sort by LastModified descending
            contents.sort(key=lambda x: x["LastModified"], reverse=True)
            last_backup_time = datetime.fromisoformat(contents[0]["LastModified"].replace("Z", "+00:00"))
            elapsed = datetime.now(timezone.utc) - last_backup_time
            if elapsed < timedelta(hours=interval_hours):
                logger.debug(
                    "Skipping auto-backup for user_id=%s: last backup was %.1fh ago (interval=%dh)",
                    s.user_id, elapsed.total_seconds() / 3600, interval_hours,
                )
                return
    except Exception as e:
        logger.warning("COS list failed for user_id=%s: %s, proceeding with backup", s.user_id, e)

    # Perform the auto-backup
    data = _gather_backup_data(db, s.user_id)
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_key = f"{auto_prefix}{timestamp}.json"

    try:
        client.put_object(
            Bucket=s.cos_bucket,
            Key=file_key,
            Body=content,
            ContentType="application/json",
        )
        logger.info("Auto backup completed for user_id=%s: key=%s, size=%d", s.user_id, file_key, len(content))
    except Exception as e:
        logger.error("Auto backup upload failed for user_id=%s: %s", s.user_id, e)
