from __future__ import annotations

import pytest

from app.api.v1 import deps
from app.core.exceptions import ForbiddenError


VALID_USER_ID = "11111111-1111-4111-8111-111111111111"
VALID_ORG_ID = "22222222-2222-4222-8222-222222222222"


def test_get_current_user_rejects_non_uuid_token_claims(monkeypatch):
    monkeypatch.setattr(
        deps,
        "safe_decode_token",
        lambda _token: {
            "sub": "user-1",
            "org_id": VALID_ORG_ID,
            "role": "algorithm_engineer",
        },
    )

    with pytest.raises(ForbiddenError, match="invalid token claims"):
        deps.get_current_user("Bearer token")


def test_get_current_user_normalizes_uuid_claims(monkeypatch):
    monkeypatch.setattr(
        deps,
        "safe_decode_token",
        lambda _token: {
            "sub": VALID_USER_ID.upper(),
            "org_id": VALID_ORG_ID.upper(),
            "role": "algorithm_engineer",
            "roles": ["algorithm_engineer"],
        },
    )

    current = deps.get_current_user("Bearer token")

    assert current.user_id == VALID_USER_ID
    assert current.org_id == VALID_ORG_ID
    assert current.role == "algorithm_engineer"
