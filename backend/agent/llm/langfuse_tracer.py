from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime
from functools import lru_cache
import logging
from typing import Any

from app.core.config import settings
from app.core.ids import uuid7


logger = logging.getLogger(__name__)


class _NoopObservation:
    def update(self, **kwargs) -> None:  # pragma: no cover - no-op helper
        return None


@lru_cache(maxsize=1)
def _get_langfuse_client():
    if not settings.langfuse_enabled:
        return None
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        logger.warning("Langfuse is enabled but public/secret key is missing")
        return None
    if any(marker in str(settings.langfuse_public_key) for marker in ["replace-me", "your_"]) or any(
        marker in str(settings.langfuse_secret_key) for marker in ["replace-me", "your_"]
    ):
        return None

    try:
        from langfuse import Langfuse
    except Exception as exc:  # pragma: no cover - depends on optional package
        logger.warning("Langfuse SDK import failed: %s", exc)
        return None

    kwargs: dict[str, Any] = {
        "public_key": settings.langfuse_public_key,
        "secret_key": settings.langfuse_secret_key,
        "host": settings.langfuse_host,
    }
    if settings.langfuse_environment:
        kwargs["environment"] = settings.langfuse_environment
    elif settings.app_env:
        kwargs["environment"] = settings.app_env
    if settings.langfuse_release:
        kwargs["release"] = settings.langfuse_release

    try:
        return Langfuse(**kwargs)
    except Exception as exc:  # pragma: no cover - depends on runtime connectivity
        logger.warning("Langfuse client init failed: %s", exc)
        return None


class LangfuseTracer:
    def __init__(self) -> None:
        self._client = _get_langfuse_client()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def create_trace_id(self, seed: str | None = None) -> str:
        if self._client is not None:
            creator = getattr(self._client, "create_trace_id", None)
            if callable(creator):
                try:
                    return str(creator(seed=seed)) if seed is not None else str(creator())
                except TypeError:
                    return str(creator())
                except Exception as exc:  # pragma: no cover - defensive runtime guard
                    logger.warning("Langfuse create_trace_id failed: %s", exc)
        return str(uuid7())

    def get_trace_url(self, trace_id: str | None) -> str | None:
        if not trace_id:
            return None
        if self._client is None:
            public_host = str(getattr(settings, "langfuse_public_host", "") or "").rstrip("/")
            return f"{public_host}/project/traces/{trace_id}" if public_host else None
        getter = getattr(self._client, "get_trace_url", None)
        if not callable(getter):
            public_host = str(getattr(settings, "langfuse_public_host", "") or "").rstrip("/")
            return f"{public_host}/project/traces/{trace_id}" if public_host else None
        try:
            return self._public_trace_url(str(getter(trace_id=trace_id)))
        except TypeError:
            try:
                return self._public_trace_url(str(getter(trace_id)))
            except Exception:
                return None
        except Exception:
            return None

    @staticmethod
    def _public_trace_url(trace_url: str | None) -> str | None:
        if not trace_url:
            return None
        internal_host = str(settings.langfuse_host or "").rstrip("/")
        public_host = str(getattr(settings, "langfuse_public_host", "") or "").rstrip("/")
        if public_host and internal_host and trace_url.startswith(internal_host):
            return public_host + trace_url[len(internal_host):]
        return trace_url

    def trace_exists(self, trace_id: str | None) -> bool | None:
        if not trace_id or self._client is None:
            return None

        trace_api = getattr(getattr(self._client, "api", None), "trace", None)
        getter = getattr(trace_api, "get", None)
        if not callable(getter):
            return None

        try:
            getter(str(trace_id), fields="id")
            return True
        except TypeError:
            try:
                getter(str(trace_id))
                return True
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                return self._handle_trace_lookup_error(trace_id, exc)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            return self._handle_trace_lookup_error(trace_id, exc)

    def _handle_trace_lookup_error(self, trace_id: str, exc: Exception) -> bool | None:
        if self._is_not_found_error(exc):
            return False
        logger.warning("Langfuse trace lookup failed for %s: %s", trace_id, exc)
        return None

    @staticmethod
    def _is_not_found_error(exc: Exception) -> bool:
        if getattr(exc, "status_code", None) == 404:
            return True

        response = getattr(exc, "response", None)
        if getattr(response, "status_code", None) == 404:
            return True

        detail_parts = [str(exc)]
        for attr in ("body", "message"):
            value = getattr(exc, attr, None)
            if value:
                detail_parts.append(str(value))

        detail = " ".join(part for part in detail_parts if part).lower()
        return "not found" in detail or "not_found" in detail or "404" in detail

    def start_trace(self, **kwargs):
        trace_id = str(kwargs.get("trace_id") or self.create_trace_id())
        payload = {
            "trace_id": trace_id,
            "task_id": kwargs.get("task_id"),
            "org_id": kwargs.get("org_id"),
            "model_key": kwargs.get("model_key"),
            "name": kwargs.get("name") or "inspection_pipeline",
            "started_at": kwargs.get("started_at") or datetime.utcnow().isoformat(),
            "trace_url": self.get_trace_url(trace_id),
        }

        if self._client is not None:
            trace_factory = getattr(self._client, "trace", None)
            if callable(trace_factory):
                metadata = {
                    key: value
                    for key, value in {
                        "task_id": payload["task_id"],
                        "org_id": payload["org_id"],
                        "model_key": payload["model_key"],
                    }.items()
                    if value is not None
                }
                try:
                    trace_factory(
                        id=trace_id,
                        name=payload["name"],
                        session_id=str(payload["task_id"]) if payload["task_id"] else None,
                        user_id=str(payload["org_id"]) if payload["org_id"] else None,
                        metadata=metadata or None,
                        input=kwargs.get("input"),
                    )
                except Exception as exc:  # pragma: no cover - defensive runtime guard
                    logger.warning("Langfuse trace creation failed: %s", exc)
        return payload

    def observe(
        self,
        *,
        trace_id: str | None,
        name: str,
        as_type: str,
        input: Any,
        model: str | None,
        model_parameters: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        if self._client is None or not trace_id:
            return nullcontext(_NoopObservation())

        starter = getattr(self._client, "start_as_current_observation", None)
        if not callable(starter):
            return nullcontext(_NoopObservation())

        kwargs: dict[str, Any] = {
            "name": name,
            "as_type": as_type,
            "trace_context": {"trace_id": str(trace_id)},
            "input": input,
            "metadata": metadata or None,
        }
        if model:
            kwargs["model"] = model
        if model_parameters:
            kwargs["model_parameters"] = model_parameters

        try:
            return starter(**kwargs)
        except TypeError:
            kwargs.pop("model_parameters", None)
            kwargs.pop("model", None)
            return starter(**kwargs)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            logger.warning("Langfuse observation creation failed: %s", exc)
            return nullcontext(_NoopObservation())

    def current_observation_id(self) -> str | None:
        if self._client is None:
            return None
        getter = getattr(self._client, "get_current_observation_id", None)
        if not callable(getter):
            return None
        try:
            observation_id = getter()
        except Exception:
            return None
        return None if observation_id is None else str(observation_id)

    def score(self, **kwargs):
        trace_id = kwargs.get("trace_id")
        payload = {
            "ok": True,
            "synced": False,
            "trace_id": trace_id,
            "observation_id": kwargs.get("observation_id"),
            "name": kwargs.get("name") or "user_feedback",
            "value": float(kwargs.get("value") or 0.0),
            "data_type": kwargs.get("data_type") or "NUMERIC",
            "comment": kwargs.get("comment"),
            "metadata": kwargs.get("metadata") or {},
            "scored_at": kwargs.get("scored_at") or datetime.utcnow().isoformat(),
            "trace_url": self.get_trace_url(str(trace_id)) if trace_id else None,
        }
        return payload

    def sync_score(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        score_payload = dict(payload or {})
        score_payload.setdefault("synced", False)
        trace_id = score_payload.get("trace_id")
        if self._client is None or not trace_id:
            return score_payload

        creator = getattr(self._client, "create_score", None)
        if not callable(creator):
            return score_payload

        kwargs: dict[str, Any] = {
            "trace_id": str(trace_id),
            "name": score_payload.get("name") or "user_feedback",
            "value": float(score_payload.get("value") or 0.0),
            "comment": score_payload.get("comment"),
            "metadata": score_payload.get("metadata") or {},
        }
        observation_id = score_payload.get("observation_id")
        if observation_id:
            kwargs["observation_id"] = str(observation_id)

        try:
            kwargs.setdefault("data_type", str(score_payload.get("data_type") or "NUMERIC"))
            creator(**kwargs)
            flusher = getattr(self._client, "flush", None)
            if callable(flusher):
                flusher()
            score_payload["synced"] = True
            score_payload["trace_url"] = score_payload.get("trace_url") or self.get_trace_url(str(trace_id))
            return score_payload
        except TypeError:
            kwargs.pop("metadata", None)
            kwargs.pop("comment", None)
            kwargs.setdefault("data_type", str(score_payload.get("data_type") or "NUMERIC"))
            creator(**kwargs)
            score_payload["synced"] = True
            score_payload["trace_url"] = score_payload.get("trace_url") or self.get_trace_url(str(trace_id))
            return score_payload
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            logger.warning("Langfuse score sync failed: %s", exc)
            return score_payload
