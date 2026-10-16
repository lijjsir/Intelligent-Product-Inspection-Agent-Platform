"""Prepare a short-lived local read-only UI verification session; do not print tokens."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy import select
from app.models.user import User
from app.core.security import create_access_token
from infra.database.session import get_session, reset_async_engine_pool

async def main():
    try:
        async with get_session() as db:
            actor = await db.scalar(select(User).where(User.org_id == '26c1c3e4-658b-498d-aab7-39b194de478c',
                User.username == 'admin', User.role == 'admin', User.is_active.is_(True)))
            assert actor
            session = {'piap_token': create_access_token(actor.id, {'org_id': actor.org_id, 'role': actor.role,
                'exp': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())}),
                'piap_role': actor.role, 'piap_roles': '["admin"]', 'piap_user_id': actor.id,
                'piap_org_id': actor.org_id, 'piap_username': actor.username}
            path = Path('runtime/industrial_catalog_view_auth.json')
            path.write_text(json.dumps(session), encoding='utf-8')
            print('临时页面核验会话已准备')
    finally:
        await reset_async_engine_pool()

asyncio.run(main())
