"""Opaque, bounded scan pages for records with per-row live authorization."""
import base64
import hashlib
import json
from datetime import datetime
from uuid import UUID

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_

from app.core.config import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.models.supervision import SupervisionRecord
from app.services.quality_risk_service import stable_hash


def cipher(purpose):
    if not settings.jwt_private_key: raise ValidationError('分页密钥配置不可用')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((purpose+'\0'+settings.jwt_private_key).encode()).digest()))


def read_mark(purpose, scope, cursor):
    if not cursor: return None
    try:
        data=json.loads(cipher(purpose).decrypt(cursor.encode(),ttl=3600))
        if data['scope']!=stable_hash(scope): raise ValueError('scope')
        mark=data['mark']; datetime.fromisoformat(mark['at']); UUID(mark['id'])
        return mark
    except (InvalidToken, ValueError, TypeError, KeyError):
        raise ValidationError('分页已失效或筛选已变化，请回到第一页') from None


def write_mark(purpose, scope, mark):
    return cipher(purpose).encrypt(json.dumps({'scope':stable_hash(scope),'mark':mark}).encode()).decode()


async def scan_records(db, query, serialize, *, scope, purpose, size=20, cursor=None):
    if not 1<=size<=50: raise ValidationError('每页数量须在 1 到 50 之间')
    mark=read_mark(purpose,scope,cursor)
    if mark:
        at=datetime.fromisoformat(mark['at'])
        query=query.where(or_(SupervisionRecord.created_at<at,(SupervisionRecord.created_at==at)&(SupervisionRecord.id<mark['id'])))
    budget=max(20,size*2)
    rows=list(await db.scalars(query.order_by(SupervisionRecord.created_at.desc(),SupervisionRecord.id.desc()).limit(budget+1).execution_options(populate_existing=True)))
    items=[]; processed=0
    for row in rows[:budget]:
        processed+=1
        try: item=await serialize(row)
        except (ForbiddenError,NotFoundError): continue
        if item is not None: items.append(item)
        if len(items)==size: break
    last=rows[processed-1] if processed else None
    more=processed<len(rows)
    token=write_mark(purpose,scope,{'at':last.created_at.isoformat(),'id':last.id}) if last and more else None
    return {'items':items,'next_cursor':token,'has_more':bool(token),'size':size}
