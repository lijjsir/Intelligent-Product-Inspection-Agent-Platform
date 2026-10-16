from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from agent.contracts.quality_contracts import NormalizedRequest
from agent.router.contracts import AgentPlanStep
from agent.router.manager_state import ManagerState
from app.services.evidence_arbitration_service import EvidenceArbitrationService
from app.services.rag_retrieval_service import RagRetrievalService


@pytest.mark.asyncio
async def test_user_knowledge_query_automatically_uses_authorized_sources(monkeypatch):
    result = {'hits':[{'source':'标准资料','quote':'可核验原文'}], 'hit_count':1}
    search = AsyncMock(return_value=result)
    monkeypatch.setattr(RagRetrievalService, 'search_authorized', search)
    state = ManagerState(request_id='r',workflow_run_id='w',org_id='org-1',surface='chat',original_query='本平台的质检标准是什么')
    request = NormalizedRequest(request_id='r',org_id='org-1',user_id='user-1',metadata={'user_role':'user'})
    content = await EvidenceArbitrationService()._retrieve_rag(step=AgentPlanStep(step_id='s1'),state=state,request=request,db_session=object())
    search.assert_awaited_once_with(query=state.original_query,top_k=5)
    assert content == [result]


@pytest.mark.asyncio
async def test_automatic_search_passes_only_own_and_system_spaces(monkeypatch):
    repo = SimpleNamespace(list_for_org=AsyncMock(return_value=[SimpleNamespace(id='own'),SimpleNamespace(id='system')]))
    monkeypatch.setattr('app.services.rag_retrieval_service.RagSpaceRepository',lambda _session:repo)
    service = RagRetrievalService(None,org_id='org-1',user_id='user-1',include_system=True)
    service.search_many = AsyncMock(return_value={'hits':[]})
    await service.search_authorized(query='监督抽查',top_k=5)
    repo.list_for_org.assert_awaited_once_with(org_id='org-1',owner_user_id='user-1',include_system=True,limit=200)
    service.search_many.assert_awaited_once_with(rag_space_ids=['own','system'],query='监督抽查',top_k=5)


@pytest.mark.asyncio
async def test_system_documents_use_the_system_owner_filter(monkeypatch):
    from infra.cache.memory_cache import _rag_space_cache, _rag_result_cache
    _rag_space_cache.clear(); _rag_result_cache.clear()
    repo = SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id='system',name='系统标准',created_by=None,updated_at=None)))
    monkeypatch.setattr('app.services.rag_retrieval_service.RagSpaceRepository',lambda _session:repo)
    service = RagRetrievalService(None,org_id='00000000-0000-0000-0000-000000000001',user_id='00000000-0000-0000-0000-000000000002',include_system=True)
    retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    service._retriever = retriever
    service._workspace_retriever = retriever
    await service.search(rag_space_id='system',query='标准',top_k=5)
    repo.get.assert_awaited_once_with(org_id='00000000-0000-0000-0000-000000000001',rag_space_id='system',owner_user_id='00000000-0000-0000-0000-000000000002',include_system=True)
    assert service._retriever.retrieve.call_args.kwargs['payload_filter'] == {'org_id':'00000000-0000-0000-0000-000000000001','user_id':None,'rag_space_id':'system'}


@pytest.mark.asyncio
async def test_missing_user_identity_cannot_enable_organization_wide_search():
    from agent.router.errors import AgentRuntimeError
    state = ManagerState(request_id='r',workflow_run_id='w',org_id='org-1',surface='chat',original_query='标准')
    request = NormalizedRequest(request_id='r',org_id='org-1',metadata={'user_role':'user'})
    with pytest.raises(AgentRuntimeError):
        await EvidenceArbitrationService()._retrieve_rag(step=AgentPlanStep(step_id='s1'),state=state,request=request,db_session=object())


@pytest.mark.asyncio
async def test_private_space_owned_by_another_user_is_not_retrieved(monkeypatch):
    from infra.cache.memory_cache import _rag_space_cache
    _rag_space_cache.clear()
    repo = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr('app.services.rag_retrieval_service.RagSpaceRepository',lambda _session:repo)
    service = RagRetrievalService(None,org_id='org-1',user_id='user-1',include_system=True)
    service._retriever = SimpleNamespace(retrieve=AsyncMock())
    result = await service.search(rag_space_id='foreign-private',query='标准')
    assert result['hit_count'] == 0
    service._retriever.retrieve.assert_not_awaited()
