from app.models.token_ledger import TokenUsageLedger


def test_token_usage_ledger_idempotency_key_allows_chat_workflow_keys():
    column = TokenUsageLedger.__table__.c.idempotency_key

    assert column.type.length == 512
