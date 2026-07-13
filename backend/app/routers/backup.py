"""
数据备份：全量导出 / 导入 + 腾讯云 COS 云端备份

导出当前用户所有业务数据为 JSON 文件，导入时按依赖顺序重建记录并重映射 ID。
支持上传到腾讯云 COS 和从 COS 恢复。
"""
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.modules.backup.service import BackupService
from app.ratelimit import limiter

router = APIRouter(prefix="/backup", tags=["backup"])

MAX_IMPORT_SIZE = 50 * 1024 * 1024  # 50MB


# ═══════════════════════════════════════════════════════════════
#  Export
# ═══════════════════════════════════════════════════════════════


@limiter.limit("10/minute")
@router.get("/export")
def export_data(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出当前用户全量数据为 JSON 文件。"""
    content, filename = BackupService(db).export_data(current_user.id)
    buf = BytesIO()
    buf.write(content)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══════════════════════════════════════════════════════════════
#  Import
# ═══════════════════════════════════════════════════════════════


@limiter.limit("3/minute")
@router.post("/import")
def import_data(
    request: Request,
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

    stats = BackupService(db).import_data(current_user.id, content)
    return {"imported": stats}


# ═══════════════════════════════════════════════════════════════
#  COS Cloud Backup
# ═══════════════════════════════════════════════════════════════


@limiter.limit("3/minute")
@router.post("/upload-to-cos")
def upload_to_cos(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """将全量数据导出并上传到腾讯云 COS（手动备份）。"""
    return BackupService(db).upload_to_cos(current_user.id)


@limiter.limit("30/minute")
@router.get("/cos-list")
def list_cos_backups(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出 COS 上的备份文件。"""
    return BackupService(db).list_cos_backups(current_user.id)


@limiter.limit("10/minute")
@router.post("/cos-delete")
def delete_cos_backup(
    request: Request,
    file_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除 COS 上的指定备份文件。"""
    return BackupService(db).delete_cos_backup(current_user.id, file_key)


@limiter.limit("10/minute")
@router.post("/cos-rename")
def rename_cos_backup(
    request: Request,
    file_key: str = Form(...),
    new_name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重命名 COS 上的备份文件（通过拷贝+删除实现）。"""
    return BackupService(db).rename_cos_backup(current_user.id, file_key, new_name)


@limiter.limit("3/minute")
@router.post("/restore-from-cos")
def restore_from_cos(
    request: Request,
    file_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从 COS 下载备份文件并导入恢复数据（覆盖模式：先清空再导入）。"""
    return BackupService(db).restore_from_cos(current_user.id, file_key)
