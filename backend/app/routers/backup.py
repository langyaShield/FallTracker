"""
数据备份：全量导出 / 导入 + 腾讯云 COS 云端备份

导出当前用户所有业务数据为 JSON 文件，导入时按依赖顺序重建记录并重映射 ID。
支持上传到腾讯云 COS 和从 COS 恢复。
"""
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.crypto import decrypt_value
from app.database import get_db
from app.models import (
    CrawlerConfig,
    CrawlerResult,
    Delivery,
    InterviewEvent,
    Notification,
    Resume,
    Review,
    User,
    UserSettings,
)

logger = logging.getLogger("falltracker")

router = APIRouter(prefix="/backup", tags=["backup"])

BACKUP_VERSION = "1.0"

# 序列化时排除的字段（内部 ID 或敏感字段）
_EXCLUDE_FIELDS = {"id", "user_id", "password_hash"}


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


# ─────────────────────────────────────────────
#  Export
# ─────────────────────────────────────────────


@router.get("/export")
def export_data(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出当前用户全量数据为 JSON 文件。"""
    uid = current_user.id

    # UserSettings
    settings = db.query(UserSettings).filter(UserSettings.user_id == uid).first()
    user_settings = _model_to_dict(settings) if settings else {}

    # CrawlerConfig + CrawlerResult
    configs = db.query(CrawlerConfig).filter(CrawlerConfig.user_id == uid).all()
    config_id_map = {c.id: idx for idx, c in enumerate(configs)}
    crawler_configs = []
    for c in configs:
        d = _model_to_dict(c)
        d["_old_id"] = c.id  # 保留旧 ID 供关联重映射
        crawler_configs.append(d)

    results = db.query(CrawlerResult).join(
        CrawlerConfig, CrawlerResult.config_id == CrawlerConfig.id
    ).filter(CrawlerConfig.user_id == uid).all()
    crawler_results = []
    for r in results:
        d = _model_to_dict(r)
        d["_old_config_id"] = r.config_id
        crawler_results.append(d)

    # Resume
    resumes = db.query(Resume).filter(Resume.user_id == uid).all()
    resume_id_map = {r.id: idx for idx, r in enumerate(resumes)}
    resume_list = []
    for r in resumes:
        d = _model_to_dict(r)
        d["_old_id"] = r.id
        resume_list.append(d)

    # Delivery
    deliveries = db.query(Delivery).filter(Delivery.user_id == uid).all()
    delivery_id_map = {d.id: idx for idx, d in enumerate(deliveries)}
    delivery_list = []
    for d in deliveries:
        dd = _model_to_dict(d)
        dd["_old_id"] = d.id
        if d.resume_id is not None:
            dd["_old_resume_id"] = d.resume_id
        delivery_list.append(dd)

    # InterviewEvent
    events = (
        db.query(InterviewEvent)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == uid)
        .all()
    )
    event_list = []
    for e in events:
        d = _model_to_dict(e)
        d["_old_delivery_id"] = e.delivery_id
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
        review_list.append(d)

    # Notification
    notifications = db.query(Notification).filter(Notification.user_id == uid).all()
    notification_list = [_model_to_dict(n) for n in notifications]

    data = {
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
    }

    buf = BytesIO()
    buf.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)

    filename = f"falltracker_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────
#  Import
# ─────────────────────────────────────────────


def _parse_datetime(val):
    """尝试解析日期时间字符串。"""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.fromisoformat(val) if "T" in str(val) else datetime.strptime(val, fmt)
        except (ValueError, TypeError):
            continue
    return None


@router.post("/import")
def import_data(
    file: UploadFile = File(...),
    mode: str = Form("merge"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导入 JSON 备份文件恢复数据。mode: merge(合并) | overwrite(覆盖)"""
    if mode not in ("merge", "overwrite"):
        raise HTTPException(status_code=400, detail="mode 必须为 merge 或 overwrite")

    # 读取并解析 JSON
    try:
        content = file.file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"无效的 JSON 文件: {e}")

    if "version" not in data:
        raise HTTPException(status_code=400, detail="无效的备份文件：缺少 version 字段")

    uid = current_user.id
    stats = {}

    # 覆盖模式：先删除当前用户所有业务数据
    if mode == "overwrite":
        # 按依赖反序删除
        db.query(Notification).filter(Notification.user_id == uid).delete()
        db.query(Review).filter(Review.user_id == uid).delete()
        db.query(InterviewEvent).filter(InterviewEvent.delivery_id.in_(
            db.query(Delivery.id).filter(Delivery.user_id == uid)
        )).delete(synchronize_session=False)
        db.query(Delivery).filter(Delivery.user_id == uid).delete()
        db.query(CrawlerResult).filter(CrawlerResult.config_id.in_(
            db.query(CrawlerConfig.id).filter(CrawlerConfig.user_id == uid)
        )).delete(synchronize_session=False)
        db.query(CrawlerConfig).filter(CrawlerConfig.user_id == uid).delete()
        db.query(Resume).filter(Resume.user_id == uid).delete()
        db.query(UserSettings).filter(UserSettings.user_id == uid).delete()
        db.commit()

    # ─── 1. UserSettings (upsert) ───
    settings_data = data.get("user_settings", {})
    if settings_data:
        existing = db.query(UserSettings).filter(UserSettings.user_id == uid).first()
        if existing:
            for key, val in settings_data.items():
                if hasattr(existing, key) and key not in _EXCLUDE_FIELDS:
                    setattr(existing, key, val)
        else:
            existing = UserSettings(user_id=uid, **{k: v for k, v in settings_data.items() if k not in _EXCLUDE_FIELDS})
            db.add(existing)
        db.flush()
    stats["user_settings"] = 1 if settings_data else 0

    # ─── 2. CrawlerConfig ───
    config_id_map = {}  # old_id -> new_id
    for item in data.get("crawler_configs", []):
        old_id = item.pop("_old_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        obj = CrawlerConfig(user_id=uid, **{k: v for k, v in item.items() if k in CrawlerConfig.__table__.columns.keys()})
        db.add(obj)
        db.flush()
        if old_id is not None:
            config_id_map[old_id] = obj.id
    stats["crawler_configs"] = len(data.get("crawler_configs", []))

    # ─── 3. CrawlerResult ───
    for item in data.get("crawler_results", []):
        old_config_id = item.pop("_old_config_id", None)
        item.pop("id", None)
        item.pop("config_id", None)
        new_config_id = config_id_map.get(old_config_id)
        if new_config_id is None:
            continue
        obj = CrawlerResult(config_id=new_config_id, **{k: v for k, v in item.items() if k in CrawlerResult.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["crawler_results"] = len(data.get("crawler_results", []))

    # ─── 4. Resume ───
    resume_id_map = {}  # old_id -> new_id
    for item in data.get("resumes", []):
        old_id = item.pop("_old_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        obj = Resume(user_id=uid, **{k: v for k, v in item.items() if k in Resume.__table__.columns.keys()})
        db.add(obj)
        db.flush()
        if old_id is not None:
            resume_id_map[old_id] = obj.id
    stats["resumes"] = len(data.get("resumes", []))

    # ─── 5. Delivery ───
    delivery_id_map = {}  # old_id -> new_id
    for item in data.get("deliveries", []):
        old_id = item.pop("_old_id", None)
        old_resume_id = item.pop("_old_resume_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        item.pop("resume_id", None)
        # 映射 resume_id
        if old_resume_id is not None and old_resume_id in resume_id_map:
            item["resume_id"] = resume_id_map[old_resume_id]
        obj = Delivery(user_id=uid, **{k: v for k, v in item.items() if k in Delivery.__table__.columns.keys()})
        db.add(obj)
        db.flush()
        if old_id is not None:
            delivery_id_map[old_id] = obj.id
    stats["deliveries"] = len(data.get("deliveries", []))

    # ─── 6. InterviewEvent ───
    for item in data.get("interview_events", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        item.pop("id", None)
        item.pop("delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        obj = InterviewEvent(delivery_id=new_delivery_id, **{k: v for k, v in item.items() if k in InterviewEvent.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["interview_events"] = len(data.get("interview_events", []))

    # ─── 7. Review ───
    for item in data.get("reviews", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        item.pop("delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        obj = Review(user_id=uid, delivery_id=new_delivery_id, **{k: v for k, v in item.items() if k in Review.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["reviews"] = len(data.get("reviews", []))

    # ─── 8. Notification ───
    for item in data.get("notifications", []):
        item.pop("id", None)
        item.pop("user_id", None)
        obj = Notification(user_id=uid, **{k: v for k, v in item.items() if k in Notification.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["notifications"] = len(data.get("notifications", []))

    db.commit()
    return {"mode": mode, "imported": stats}


# ─────────────────────────────────────────────
#  COS Cloud Backup
# ─────────────────────────────────────────────


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
        raise HTTPException(status_code=400, detail=f"COS 配置错误: {e}")


def _build_backup_json(db: Session, uid: int) -> bytes:
    """构建全量备份 JSON 字节。"""
    settings = db.query(UserSettings).filter(UserSettings.user_id == uid).first()
    user_settings = _model_to_dict(settings) if settings else {}

    configs = db.query(CrawlerConfig).filter(CrawlerConfig.user_id == uid).all()
    crawler_configs = []
    for c in configs:
        d = _model_to_dict(c)
        d["_old_id"] = c.id
        crawler_configs.append(d)

    results = db.query(CrawlerResult).join(
        CrawlerConfig, CrawlerResult.config_id == CrawlerConfig.id
    ).filter(CrawlerConfig.user_id == uid).all()
    crawler_results = []
    for r in results:
        d = _model_to_dict(r)
        d["_old_config_id"] = r.config_id
        crawler_results.append(d)

    resumes = db.query(Resume).filter(Resume.user_id == uid).all()
    resume_list = []
    for r in resumes:
        d = _model_to_dict(r)
        d["_old_id"] = r.id
        resume_list.append(d)

    deliveries = db.query(Delivery).filter(Delivery.user_id == uid).all()
    delivery_list = []
    for d in deliveries:
        dd = _model_to_dict(d)
        dd["_old_id"] = d.id
        if d.resume_id is not None:
            dd["_old_resume_id"] = d.resume_id
        delivery_list.append(dd)

    events = (
        db.query(InterviewEvent)
        .join(Delivery, InterviewEvent.delivery_id == Delivery.id)
        .filter(Delivery.user_id == uid)
        .all()
    )
    event_list = []
    for e in events:
        d = _model_to_dict(e)
        d["_old_delivery_id"] = e.delivery_id
        event_list.append(d)

    reviews_q = (
        db.query(Review)
        .join(Delivery, Review.delivery_id == Delivery.id)
        .filter(Delivery.user_id == uid)
        .all()
    )
    review_list = []
    for r in reviews_q:
        d = _model_to_dict(r)
        d["_old_delivery_id"] = r.delivery_id
        review_list.append(d)

    notifications = db.query(Notification).filter(Notification.user_id == uid).all()
    notification_list = [_model_to_dict(n) for n in notifications]

    data = {
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
    }
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


@router.post("/upload-to-cos")
def upload_to_cos(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将全量数据导出并上传到腾讯云 COS。"""
    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    client, bucket, region = _get_cos_client(s)
    path_prefix = (s.cos_path or "backups/").rstrip("/") + "/"

    content = _build_backup_json(db, current_user.id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_key = f"{path_prefix}falltracker_{timestamp}.json"

    try:
        client.put_object(
            Bucket=bucket,
            Key=file_key,
            Body=content,
            ContentType="application/json",
        )
    except Exception as e:
        logger.error("COS upload failed: %s", e)
        raise HTTPException(status_code=500, detail=f"上传到 COS 失败: {e}")

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
        raise HTTPException(status_code=500, detail=f"获取 COS 文件列表失败: {e}")

    files = []
    for obj in resp.get("Contents", []):
        files.append({
            "key": obj["Key"],
            "size": obj["Size"],
            "last_modified": obj["LastModified"],
        })
    files.sort(key=lambda x: x["last_modified"], reverse=True)
    return files


@router.post("/restore-from-cos")
def restore_from_cos(
    file_key: str = Form(...),
    mode: str = Form("merge"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从 COS 下载备份文件并导入恢复数据。"""
    if mode not in ("merge", "overwrite"):
        raise HTTPException(status_code=400, detail="mode 必须为 merge 或 overwrite")

    s = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not s:
        raise HTTPException(status_code=400, detail="请先在设置中配置腾讯云 COS 参数")

    client, bucket, region = _get_cos_client(s)

    try:
        resp = client.get_object(Bucket=bucket, Key=file_key)
        content = resp["Body"].read()
    except Exception as e:
        logger.error("COS download failed: %s", e)
        raise HTTPException(status_code=500, detail=f"从 COS 下载失败: {e}")

    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(status_code=400, detail=f"无效的 JSON 文件: {e}")

    if "version" not in data:
        raise HTTPException(status_code=400, detail="无效的备份文件：缺少 version 字段")

    # 复用导入逻辑
    uid = current_user.id
    stats = {}

    if mode == "overwrite":
        db.query(Notification).filter(Notification.user_id == uid).delete()
        db.query(Review).filter(Review.user_id == uid).delete()
        db.query(InterviewEvent).filter(InterviewEvent.delivery_id.in_(
            db.query(Delivery.id).filter(Delivery.user_id == uid)
        )).delete(synchronize_session=False)
        db.query(Delivery).filter(Delivery.user_id == uid).delete()
        db.query(CrawlerResult).filter(CrawlerResult.config_id.in_(
            db.query(CrawlerConfig.id).filter(CrawlerConfig.user_id == uid)
        )).delete(synchronize_session=False)
        db.query(CrawlerConfig).filter(CrawlerConfig.user_id == uid).delete()
        db.query(Resume).filter(Resume.user_id == uid).delete()
        db.query(UserSettings).filter(UserSettings.user_id == uid).delete()
        db.commit()

    settings_data = data.get("user_settings", {})
    if settings_data:
        existing = db.query(UserSettings).filter(UserSettings.user_id == uid).first()
        if existing:
            for key, val in settings_data.items():
                if hasattr(existing, key) and key not in _EXCLUDE_FIELDS:
                    setattr(existing, key, val)
        else:
            existing = UserSettings(user_id=uid, **{k: v for k, v in settings_data.items() if k not in _EXCLUDE_FIELDS})
            db.add(existing)
        db.flush()
    stats["user_settings"] = 1 if settings_data else 0

    config_id_map = {}
    for item in data.get("crawler_configs", []):
        old_id = item.pop("_old_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        obj = CrawlerConfig(user_id=uid, **{k: v for k, v in item.items() if k in CrawlerConfig.__table__.columns.keys()})
        db.add(obj)
        db.flush()
        if old_id is not None:
            config_id_map[old_id] = obj.id
    stats["crawler_configs"] = len(data.get("crawler_configs", []))

    for item in data.get("crawler_results", []):
        old_config_id = item.pop("_old_config_id", None)
        item.pop("id", None)
        item.pop("config_id", None)
        new_config_id = config_id_map.get(old_config_id)
        if new_config_id is None:
            continue
        obj = CrawlerResult(config_id=new_config_id, **{k: v for k, v in item.items() if k in CrawlerResult.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["crawler_results"] = len(data.get("crawler_results", []))

    resume_id_map = {}
    for item in data.get("resumes", []):
        old_id = item.pop("_old_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        obj = Resume(user_id=uid, **{k: v for k, v in item.items() if k in Resume.__table__.columns.keys()})
        db.add(obj)
        db.flush()
        if old_id is not None:
            resume_id_map[old_id] = obj.id
    stats["resumes"] = len(data.get("resumes", []))

    delivery_id_map = {}
    for item in data.get("deliveries", []):
        old_id = item.pop("_old_id", None)
        old_resume_id = item.pop("_old_resume_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        item.pop("resume_id", None)
        if old_resume_id is not None and old_resume_id in resume_id_map:
            item["resume_id"] = resume_id_map[old_resume_id]
        obj = Delivery(user_id=uid, **{k: v for k, v in item.items() if k in Delivery.__table__.columns.keys()})
        db.add(obj)
        db.flush()
        if old_id is not None:
            delivery_id_map[old_id] = obj.id
    stats["deliveries"] = len(data.get("deliveries", []))

    for item in data.get("interview_events", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        item.pop("id", None)
        item.pop("delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        obj = InterviewEvent(delivery_id=new_delivery_id, **{k: v for k, v in item.items() if k in InterviewEvent.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["interview_events"] = len(data.get("interview_events", []))

    for item in data.get("reviews", []):
        old_delivery_id = item.pop("_old_delivery_id", None)
        item.pop("id", None)
        item.pop("user_id", None)
        item.pop("delivery_id", None)
        new_delivery_id = delivery_id_map.get(old_delivery_id)
        if new_delivery_id is None:
            continue
        obj = Review(user_id=uid, delivery_id=new_delivery_id, **{k: v for k, v in item.items() if k in Review.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["reviews"] = len(data.get("reviews", []))

    for item in data.get("notifications", []):
        item.pop("id", None)
        item.pop("user_id", None)
        obj = Notification(user_id=uid, **{k: v for k, v in item.items() if k in Notification.__table__.columns.keys()})
        db.add(obj)
    db.flush()
    stats["notifications"] = len(data.get("notifications", []))

    db.commit()
    return {"mode": mode, "source": "cos", "file_key": file_key, "imported": stats}
