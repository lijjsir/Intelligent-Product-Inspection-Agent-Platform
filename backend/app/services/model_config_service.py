from __future__ import annotations

import base64
import hashlib
from typing import Any

from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.ids import uuid7
from app.repositories.model_config_repo import ModelConfigRepository
from app.services.base import TenantAwareService
from infra.cache.memory_cache import _model_config_cache


def _fernet() -> Fernet:
    seed = getattr(settings, "governance_secret", settings.jwt_private_key or settings.jwt_public_key or "piap-governance")
    digest = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


class ModelConfigService(TenantAwareService):
    def __init__(self, session, org_id: str):
        super().__init__(session, org_id)
        self._repo = ModelConfigRepository(session)

    async def list_configs(self) -> list:
        return await self._repo.list_all(self._org_id)

    async def get_config(self, config_id: str):
        model = await self._repo.get(self._org_id, config_id)
        if not model:
            raise NotFoundError("model config not found")
        return model

    async def create_config(self, payload: dict[str, Any]):
        body = dict(payload)
        body["id"] = str(uuid7())
        body["org_id"] = body.get("org_id") or self._org_id
        if body.get("api_key"):
            body["api_key_enc"] = _fernet().encrypt(str(body.pop("api_key")).encode("utf-8")).decode("utf-8")
        body.setdefault("health_status", "unknown")
        body.setdefault("health_message", None)
        created = await self._repo.create(body)
        await self._session.commit()
        _model_config_cache.delete_prefix(f"models:{self._org_id}:")
        return created

    async def update_config(self, config_id: str, payload: dict[str, Any]):
        model = await self.get_config(config_id)
        body = {k: v for k, v in payload.items() if v is not None}
        if "api_key" in body:
            value = body.pop("api_key")
            body["api_key_enc"] = _fernet().encrypt(str(value).encode("utf-8")).decode("utf-8") if value else None
        updated = await self._repo.save(model, body)
        await self._session.commit()
        _model_config_cache.delete_prefix(f"models:{self._org_id}:")
        return updated

    async def delete_config(self, config_id: str) -> None:
        model = await self.get_config(config_id)
        await self._repo.delete(model)
        await self._session.commit()
        _model_config_cache.delete_prefix(f"models:{self._org_id}:")

    async def list_runtime_models(self, model_type: str | None = None) -> list[dict[str, Any]]:
        normalized_type = str(model_type or "all").strip().lower() or "all"
        cache_key = f"models:{self._org_id}:{normalized_type}"
        cached = _model_config_cache.get(cache_key)
        if cached is not None:
            return cached
        models = await self._repo.list_active(self._org_id)
        result = [
            self.to_runtime_payload(item)
            for item in models
            if normalized_type == "all" or str(getattr(item, "model_type", "") or "").lower() == normalized_type
        ]
        _model_config_cache.set(cache_key, result, ttl_seconds=30)
        return result

    @staticmethod
    def invalidate_runtime_cache(org_id: str) -> None:
        _model_config_cache.delete_prefix(f"models:{org_id}:")

    @staticmethod
    def decrypt_api_key(value: str | None) -> str | None:
        if not value:
            return None
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")

    @classmethod
    def to_runtime_payload(cls, model) -> dict[str, Any]:
        return {
            "id": model.id,
            "org_id": model.org_id,
            "provider": model.provider,
            "model_key": model.model_key,
            "endpoint": model.endpoint,
            "model_type": model.model_type,
            "training_command_template": getattr(model, "training_command_template", None),
            "fine_tune_command_template": getattr(model, "fine_tune_command_template", None),
            "offline_eval_command_template": getattr(model, "offline_eval_command_template", None),
            "deployment_command_template": getattr(model, "deployment_command_template", None),
            "runtime_env_json": getattr(model, "runtime_env_json", None),
            "default_gpu_request": getattr(model, "default_gpu_request", None),
            "default_cpu_request": getattr(model, "default_cpu_request", None),
            "default_memory_gb": getattr(model, "default_memory_gb", None),
            "priority": model.priority,
            "rpm_limit": model.rpm_limit,
            "input_price_per_million": float(model.input_price_per_million)
            if getattr(model, "input_price_per_million", None) is not None else None,
            "output_price_per_million": float(model.output_price_per_million)
            if getattr(model, "output_price_per_million", None) is not None else None,
            "is_active": model.is_active,
            "health_status": model.health_status,
            "health_message": model.health_message,
            "api_key": cls.decrypt_api_key(model.api_key_enc) if getattr(model, "api_key_enc", None) else None,
        }
