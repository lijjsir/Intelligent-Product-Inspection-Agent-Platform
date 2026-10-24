"""Read local model configs and issue bounded, synthetic JSON connectivity probes.

Run in the existing local backend container; never prints endpoints or credentials.
This is not an evidence, business quality, or full workflow acceptance test.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.model_config import ModelConfig
from app.services.model_config_service import ModelConfigService
from agent.llm.client import LLMClient
from agent.llm.gateway import LLMGateway
from agent.subgraphs.supervision.agents import parse_model_json
from infra.database.session import _engine


class ProbeClient(LLMClient):
    def _build_chat_payload(self, *args, **kwargs):
        return {**super()._build_chat_payload(*args, **kwargs), 'max_tokens':128}


async def probe(keys):
    if settings.app_env not in {'dev', 'local', 'test', 'testing', 'development'}:
        raise RuntimeError('Only run this probe in a local or test backend')
    # The probe does not need tracing, pricing writes, or health configuration writes.
    settings.langfuse_enabled = False
    items = []
    async with AsyncSession(_engine) as db:
        rows = list(await db.scalars(select(ModelConfig).where(ModelConfig.is_active.is_(True), ModelConfig.model_key.in_(keys))))
        for row in rows:
            result = {'model':row.model_key, 'model_type':row.model_type, 'ok':False}
            started = time.monotonic()
            try:
                runtime = await LLMGateway().select_runtime(models=[ModelConfigService.to_runtime_payload(row)],
                    model_types={'chat','llm','text_generation'}, reserve=False)
                if not runtime:
                    result['error_type'] = 'NoCompatibleRuntime'
                else:
                    client = ProbeClient(api_key=runtime.get('api_key'), base_url=runtime.get('base_url'),
                        model_id=runtime.get('model_id'), provider=runtime.get('provider'))
                    client._request_attempts = 1
                    response = await asyncio.wait_for(client.chat([{'role':'user',
                        'content':'Health check. Return only the JSON object {"ok":true}.'}], temperature=0), timeout=25)
                    result['ok'] = parse_model_json(response) == {'ok':True}
                    result['usage'] = response.get('usage') or (response.get('__meta__') or {}).get('usage')
            except Exception as exc:
                # Error strings may contain request URLs or credentials. Report only type.
                result['error_type'] = type(exc).__name__
                response = getattr(exc, 'response', None)
                if response is not None:result['http_status'] = response.status_code
            result['elapsed_seconds'] = round(time.monotonic()-started, 2)
            items.append(result)
    for key in set(keys)-{r.model_key for r in rows}:
        items.append({'model':key, 'ok':False, 'error_type':'MissingActiveConfig'})
    print(json.dumps({'checked_at':datetime.now(timezone.utc).isoformat(), 'synthetic_probe_only':True,
        'business_data_sent':False, 'results':items}, ensure_ascii=False))


async def run_probe(keys):
    try:
        await probe(keys)
    finally:
        await _engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-key', action='append', required=True)
    args = parser.parse_args()
    if not 1 <= len(args.model_key) <= 4:
        parser.error('Choose one to four model keys')
    asyncio.run(run_probe(list(dict.fromkeys(args.model_key))))
