from types import SimpleNamespace
from unittest.mock import AsyncMock
from contextlib import asynccontextmanager

import pytest
from app.repositories.chat_repo import ChatSessionRepository
from app.services import chat_title_service as titles
from app.services.chat_service import ChatService
from app.schemas.user import CurrentUser
from app.core.exceptions import NotFoundError


@pytest.mark.asyncio
async def test_preference_updates_reject_a_session_not_owned_by_the_user(monkeypatch):
    db = SimpleNamespace(commit=AsyncMock())
    @asynccontextmanager
    async def session():
        yield db
    monkeypatch.setattr('app.services.chat_service.get_session',session)
    update = AsyncMock(return_value=None)
    monkeypatch.setattr(ChatSessionRepository,'update_preferences',update)
    service = ChatService(org_id='org-1',user_id='user-1',current=CurrentUser(user_id='user-1',org_id='org-1',role='user'))
    with pytest.raises(NotFoundError):
        await service.update_session('foreign',title='新标题')
    update.assert_awaited_once_with('org-1','user-1','foreign',title='新标题',is_pinned=None)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_rename_and_pin_are_saved_together():
    row = SimpleNamespace(title='AI 标题',title_source='ai',is_pinned=False)
    db = SimpleNamespace(flush=AsyncMock())
    repo = ChatSessionRepository(db)
    repo.get = AsyncMock(return_value=row)
    result = await repo.update_preferences('org','user','session',title='我的标题',is_pinned=True)
    assert result.title == '我的标题'
    assert result.title_source == 'manual'
    assert result.is_pinned is True
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_title_generation_skips_manually_named_conversations(monkeypatch):
    @asynccontextmanager
    async def session():
        yield object()
    monkeypatch.setattr(titles,'get_session',session)
    monkeypatch.setattr(ChatSessionRepository,'get',AsyncMock(return_value=SimpleNamespace(title_source='manual')))
    summarize = AsyncMock()
    monkeypatch.setattr(titles,'summarize_title',summarize)
    await titles.generate_title('org','user','session')
    summarize.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('source',['auto','fallback'])
async def test_completed_conversation_gets_an_ai_topic_title(monkeypatch,source):
    db = SimpleNamespace(commit=AsyncMock())
    @asynccontextmanager
    async def session():
        yield db
    monkeypatch.setattr(titles,'get_session',session)
    monkeypatch.setattr(ChatSessionRepository,'get',AsyncMock(return_value=SimpleNamespace(title_source=source)))
    messages = [SimpleNamespace(role='user',message_type='text',content='查看图片是否有损伤'),SimpleNamespace(role='assistant',message_type='visual_answer',content='榛子果仁存在缺损')]
    monkeypatch.setattr('app.repositories.chat_repo.ChatMessageRepository.list_for_session',AsyncMock(return_value=messages))
    monkeypatch.setattr(titles,'summarize_title',AsyncMock(return_value='榛子果仁缺损分析'))
    saved = AsyncMock()
    monkeypatch.setattr(ChatSessionRepository,'set_automatic_title',saved)
    await titles.generate_title('org','user','session')
    saved.assert_awaited_once_with('org','user','session','榛子果仁缺损分析','ai')


@pytest.mark.asyncio
async def test_late_ai_title_cannot_overwrite_manual_edit():
    from sqlalchemy.dialects import mysql
    db = SimpleNamespace(execute=AsyncMock())
    await ChatSessionRepository(db).set_automatic_title('org','user','session','主题','ai')
    sql = str(db.execute.call_args.args[0].compile(dialect=mysql.dialect()))
    assert 'chat_sessions.title_source IN' in sql.split('WHERE',1)[1]
    assert 'chat_sessions.user_id =' in sql.split('WHERE',1)[1]
    assert 'chat_sessions.deleted_at IS NULL' in sql


def test_title_migration_preserves_existing_custom_titles():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine,text,inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1]/'migrations/versions/0104_chat_session_preferences.py'
    spec = importlib.util.spec_from_file_location('chat_preferences_migration',path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    engine = create_engine('sqlite:///:memory:')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE chat_sessions (title VARCHAR(120))'))
        db.execute(text("INSERT INTO chat_sessions (title) VALUES ('2026-10-01 21:11'),('我的自定义标题')"))
        module.op = Operations(MigrationContext.configure(db))
        module.upgrade()
        rows = db.execute(text('SELECT title,title_source,is_pinned FROM chat_sessions')).all()
        assert rows[0][1:] == ('auto',0)
        assert rows[1][1:] == ('manual',0)


def test_titles_do_not_use_dates_or_identifiers():
    assert titles.clean_title('2026-10-01 21:11') == ''
    assert titles.clean_title('标题：榛子果仁检测') == '榛子果仁检测'


@pytest.mark.asyncio
async def test_title_summary_uses_existing_llm_client_contract(monkeypatch):
    from agent.llm.client import LLMClient
    from agent.llm.gateway import LLMGateway
    from app.services.model_config_service import ModelConfigService

    @asynccontextmanager
    async def session():
        yield object()
    monkeypatch.setattr(titles,'get_session',session)
    monkeypatch.setattr(ModelConfigService,'list_runtime_models',AsyncMock(return_value=[]))
    monkeypatch.setattr(LLMGateway,'select_runtime',AsyncMock(return_value={'model_id':'chat-model','provider':'local_openai','base_url':'http://localhost:9000/v1'}))
    post=AsyncMock(return_value={'title':'检测图片资料准备'})
    monkeypatch.setattr(LLMClient,'_post_json',post)
    result=await titles.summarize_title('org','user: 检测前要准备什么图片？\nassistant: 请准备整体和局部图片。')
    assert result=='检测图片资料准备'
    assert post.call_args.args[0]=='/chat/completions'
    assert post.call_args.args[1]['model']=='chat-model'
