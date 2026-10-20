"""Local MySQL probe using connection-local temporary tables and read-only inboxes.

No business rows, credentials, schema migrations, messages or approvals are changed.
Run inside the existing local backend container.
"""
import argparse
import asyncio
import json
from uuid import uuid4

from sqlalchemy import Column, LargeBinary, MetaData, String, Table, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.user import User
from app.services.collab_service import CollabService
from app.services.collab_work_item_page_service import CollabWorkItemPageService, _ScopeUUIDText
from app.services.risk_report_listing_service import uuid_text
from infra.database.session import get_session, _engine


async def main(username):
    from sqlalchemy.engine import make_url
    url=make_url(settings.db_url)
    if settings.app_env not in {'dev','local','test','development','testing'} or url.host not in {'mysql','localhost','127.0.0.1','::1'}:
        raise RuntimeError('This probe is restricted to the existing local development database')
    engine=create_async_engine(settings.db_url,poolclass=NullPool,echo=False)
    room_id=uuid4();other=uuid4();reproduced=False;checks=[]
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET SESSION collation_connection = 'utf8mb4_0900_ai_ci'"))
            suffix=uuid4().hex[:12];room_name='collab_room_probe_'+suffix
            await conn.execute(text(f'CREATE TEMPORARY TABLE {room_name} (id BINARY(16) PRIMARY KEY)'))
            await conn.execute(text(f'INSERT INTO {room_name} (id) VALUES (:id)'),{'id':room_id.bytes})
            rooms=Table(room_name,MetaData(),Column('id',LargeBinary(16)))
            for collation in ('utf8mb4_unicode_ci','utf8mb4_0900_ai_ci'):
                scope_name='collab_scope_probe_'+suffix+('_old' if collation.endswith('unicode_ci') else '_new')
                await conn.execute(text(f'CREATE TEMPORARY TABLE {scope_name} (scope_id VARCHAR(128) CHARACTER SET utf8mb4 COLLATE {collation})'))
                await conn.execute(text(f'INSERT INTO {scope_name} (scope_id) VALUES (:same),(:other)'),{'same':str(room_id),'other':str(other)})
                scopes=Table(scope_name,MetaData(),Column('scope_id',String(128)))
                raw=select(scopes.c.scope_id).select_from(rooms.join(scopes,uuid_text(rooms.c.id)==scopes.c.scope_id))
                try:await conn.execute(raw)
                except OperationalError as error:
                    if error.orig.args[0]!=1267:raise
                    reproduced=True
                fixed=select(scopes.c.scope_id).select_from(rooms.join(scopes,_ScopeUUIDText(uuid_text(rooms.c.id))==scopes.c.scope_id))
                values=list(await conn.scalars(fixed))
                assert values==[str(room_id)],'Only the matching UUID scope may be returned'
                checks.append({'scope_collation':collation,'matching_uuid_only':True})
        assert reproduced,'Expected mixed-collation reproduction was not observed'
    finally:
        # NullPool closes the connection; MySQL removes its temporary tables.
        await engine.dispose()
    inboxes={}
    filters={}
    async with get_session() as session:
        users=list(await session.scalars(select(User).where(User.username==username,User.is_active.is_(True),User.deleted_at.is_(None))))
        if len(users)!=1:raise RuntimeError('Choose an unambiguous active local username for the read-only inbox check')
        user=users[0]
        pager=CollabWorkItemPageService(CollabService(session,str(user.org_id),str(user.id),role=user.role))
        for view in ('pending','initiated','processed'):
            page=await pager.page(view=view,size=20)
            inboxes[view]={'loaded':True,'shown':len(page['items']),'has_more':page['has_more']}
        for label,options in (
            ('action_request',{'item_type':'action_request'}),('memory_share',{'item_type':'memory_share'}),
            ('meeting_scope',{'scope_type':'meeting_room'}),('room_filter',{'room_id':str(uuid4())}),
            ('keyword',{'keyword':'collab-compatibility-probe-no-match'}),
        ):
            page=await pager.page(view='pending',size=20,**options)
            filters[label]={'loaded':True,'shown':len(page['items'])}
        await session.rollback()
    await _engine.dispose()
    print(json.dumps({'passed':True,'legacy_1267_reproduced':reproduced,'mysql_comparison_checks':checks,
        'local_inboxes':inboxes,'local_filters':filters,'business_rows_changed':False,'permanent_schema_changed':False},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--username',default='expert')
    asyncio.run(main(parser.parse_args().username))
