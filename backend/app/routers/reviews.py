import re
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Review, Delivery, User
from app.schemas import ReviewCreate, ReviewUpdate, ReviewOut
from app.auth import get_current_user
from app.routers.settings import get_llm_config
import httpx

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("", response_model=List[ReviewOut])
def list_reviews(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Review).filter(Review.user_id == current_user.id).all()


@router.post("", response_model=ReviewOut)
def create_review(data: ReviewCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    delivery = db.query(Delivery).filter(Delivery.id == data.delivery_id, Delivery.user_id == current_user.id).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    db_item = Review(**data.model_dump(), user_id=current_user.id)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/{review_id}", response_model=ReviewOut)
def update_review(review_id: int, data: ReviewUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post("/{review_id}/generate")
async def generate_structured(review_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.query(Review).filter(Review.id == review_id, Review.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Review not found")

    # Use per-user LLM config with global fallback
    llm = get_llm_config(db, current_user.id)
    if not llm["llm_api_key"]:
        raise HTTPException(status_code=500, detail="LLM API key not configured. Please go to Settings to configure.")

    # Sanitize user input to mitigate prompt injection
    safe_notes = item.raw_notes[:3000].replace("```", "'''").replace("<|", "< |")
    prompt = f"""你是一位资深技术面试官和职业导师。请根据以下面试复盘笔记，提取核心面试问答，补全标准答案，并给出面试表现反思。

面试笔记：
{safe_notes}

请按以下 JSON 格式输出：
{{
  "qa_pairs": [
    {{"question": "问题", "answer": "标准答案", "leetcode_link": "相关LeetCode题链接(如有)"}}
  ],
  "tags": ["技术标签"],
  "reflection": "面试表现反思与改进建议"
}}"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{llm['llm_api_base']}/chat/completions",
                headers={"Authorization": f"Bearer {llm['llm_api_key']}"},
                json={
                    "model": llm["llm_model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
                timeout=60,
            )
            resp.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="LLM API 请求超时，请稍后重试")
    except httpx.ConnectError:
        raise HTTPException(status_code=502, detail="无法连接 LLM API 服务，请检查 API Base 配置")
    except httpx.HTTPStatusError as e:
        status_code = e.response.status_code
        if status_code == 401:
            raise HTTPException(status_code=401, detail="LLM API Key 无效，请检查设置")
        elif status_code == 429:
            raise HTTPException(status_code=429, detail="LLM API 请求频率超限，请稍后重试")
        else:
            raise HTTPException(status_code=502, detail=f"LLM API 返回错误 (HTTP {status_code})")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"LLM API 请求失败: {str(e)[:100]}")

    try:
        content = resp.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            structured = json.loads(match.group())
            item.structured_qa = structured.get("qa_pairs")
            item.tags = structured.get("tags", [])
            item.reflection = structured.get("reflection", "")
            db.commit()
            db.refresh(item)
            return {"ok": True}
        raise HTTPException(status_code=500, detail="Failed to parse LLM response")
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=500, detail=f"LLM 返回内容解析失败: {str(e)[:100]}")
