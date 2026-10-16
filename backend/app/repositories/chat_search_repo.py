"""Search owned conversation text and attachment names without loading full histories."""
from sqlalchemy import Text, case, cast, func, or_, select, true
from app.models.chat import ChatMessage, ChatSession


def filename_match(query: str):
    pattern = '%' + query.lower().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
    return func.json_search(func.lower(cast(ChatMessage.payload, Text)), 'one', pattern, None, '$.attachment_echo[*].name').is_not(None)


def attachment_kind(kind: str):
    values = ['image'] if kind == 'image' else ['file', 'document']
    return or_(*(func.json_search(ChatMessage.payload, 'one', value, None, '$.attachment_echo[*].kind').is_not(None) for value in values))


class ChatSearchRepository:
    def __init__(self, session):
        self._session = session

    async def search(self, org_id: str, user_id: str, query: str, kind: str, limit: int, offset: int):
        message_scope = [ChatMessage.org_id == org_id, ChatMessage.deleted_at.is_(None), ChatMessage.role.in_(['user', 'assistant']), ChatMessage.message_type != 'streaming']
        match = (ChatMessage.content.icontains(query, autoescape=True) if kind == 'chat' else or_(ChatMessage.content.icontains(query, autoescape=True), filename_match(query))) if query else true()
        owned_messages = select(ChatMessage.id).where(*message_scope, ChatMessage.session_id == ChatSession.id).correlate(ChatSession)
        scope = [ChatSession.org_id == org_id, ChatSession.user_id == user_id, ChatSession.deleted_at.is_(None), owned_messages.exists()]
        if query:
            scope.append(or_(ChatSession.title.icontains(query, autoescape=True), owned_messages.where(match).exists()))
        if kind in {'image', 'file'}:
            scope.append(owned_messages.where(attachment_kind(kind)).exists())
        total = int(await self._session.scalar(select(func.count()).select_from(ChatSession).where(*scope)) or 0)
        rows = list((await self._session.execute(select(ChatSession).where(*scope).order_by(ChatSession.is_pinned.desc(), ChatSession.last_message_at.desc(), ChatSession.updated_at.desc(), ChatSession.id.desc()).limit(limit).offset(offset))).scalars().all())
        if not rows:
            return [], {}, total
        # One relevant message per conversation, including matches far beyond the latest page.
        relevance = match
        ordering = [case((match, 0), else_=1)]
        if kind in {'image', 'file'}:
            relevance = match & attachment_kind(kind)
            ordering = [case((relevance, 0), else_=1), case((attachment_kind(kind), 0), else_=1)]
        ranked = select(ChatMessage.id.label('message_id'), func.row_number().over(partition_by=ChatMessage.session_id, order_by=(*ordering, ChatMessage.seq_no.asc())).label('rank')).where(*message_scope, ChatMessage.session_id.in_([row.id for row in rows])).subquery()
        messages = (await self._session.execute(select(ChatMessage).join(ranked, ranked.c.message_id == ChatMessage.id).where(ranked.c.rank == 1))).scalars().all()
        return rows, {str(row.session_id): row for row in messages}, total
