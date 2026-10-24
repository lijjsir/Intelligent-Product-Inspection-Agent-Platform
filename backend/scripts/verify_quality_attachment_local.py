"""Read-only loopback verification of the existing public report and page endpoint."""
from __future__ import annotations
import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx

from app.core.claims import build_auth_claims
from app.core.security import create_access_token
from infra.database.session import get_session, reset_async_engine_pool
from scripts.import_quality_public_cases import actors, REPORT_SHA256


async def main():
    root = Path('runtime/real_quality_case_20261023')
    index = json.loads((root / 'case-index.json').read_text(encoding='utf-8'))
    async with get_session() as db:
        org, users = await actors(db)
        user = users['expert']
        extra = build_auth_claims(user.role, getattr(org, 'plan', None)).as_token_extra(org.id)
        token = create_access_token(user.user_id, {**extra, 'exp': int(time.time()) + 180})
    await reset_async_engine_pool()
    path = '/api/v1/quality-data/attachments/' + index['report_attachment']
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', headers={'Authorization':'Bearer '+token}, timeout=45) as client:
        original = await client.get(path + '/download')
        original.raise_for_status()
        assert hashlib.sha256(original.content).hexdigest() == REPORT_SHA256
        pages = await asyncio.gather(*(client.get(path + f'/pages/{number}/preview') for number in [1,3,5]))
        for response in pages:
            response.raise_for_status()
            assert response.headers['x-pdf-page-count'] == '8'
            assert response.headers['x-original-sha256'] == REPORT_SHA256
            assert response.content.startswith(b'\x89PNG\r\n\x1a\n')
        invalid = await client.get(path + '/pages/9/preview')
        assert invalid.status_code == 422
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=15) as client:
        unauthenticated = await client.get(path + '/pages/1/preview')
        assert unauthenticated.status_code in [401,403]
    result = {'scope':'local loopback only; read-only', 'original_present':True, 'original_sha256':REPORT_SHA256,
        'pdf_page_count':8, 'rendered_pages':[1,3,5], 'invalid_page_status':invalid.status_code,
        'unauthenticated_status':unauthenticated.status_code, 'business_data_writes':0, 'token_saved_or_printed':False}
    output = Path('runtime/local_quality_release/quality-original-verification.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
