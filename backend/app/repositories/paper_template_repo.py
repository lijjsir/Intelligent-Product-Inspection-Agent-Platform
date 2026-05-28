from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paper_template import PaperTemplate, PaperTemplateClause, PaperTemplateRule
from app.repositories.base import BaseRepository


class PaperTemplateRepository(BaseRepository[PaperTemplate]):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_template_id(self, template_id: str) -> PaperTemplate | None:
        stmt = select(PaperTemplate).where(PaperTemplate.template_id == template_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_template(self, template: PaperTemplate) -> PaperTemplate:
        existing = await self.get_by_template_id(template.template_id)
        if existing:
            for key, value in template.__dict__.items():
                if key != "id" and not key.startswith("_"):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        self._session.add(template)
        await self._session.flush()
        await self._session.refresh(template)
        return template


class PaperTemplateClauseRepository(BaseRepository[PaperTemplateClause]):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def get_by_template_and_clause(self, template_id: str, clause_id: str) -> PaperTemplateClause | None:
        stmt = select(PaperTemplateClause).where(
            PaperTemplateClause.template_id == template_id,
            PaperTemplateClause.clause_id == clause_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_template(self, template_id: str) -> list[PaperTemplateClause]:
        stmt = select(PaperTemplateClause).where(PaperTemplateClause.template_id == template_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_template(self, template_id: str) -> int:
        result = await self._session.execute(
            select(PaperTemplateClause).where(PaperTemplateClause.template_id == template_id)
        )
        clauses = result.scalars().all()
        for clause in clauses:
            await self._session.delete(clause)
        return len(clauses)

    async def upsert_clause(self, clause: PaperTemplateClause) -> PaperTemplateClause:
        existing = await self.get_by_template_and_clause(clause.template_id, clause.clause_id)
        if existing:
            for key, value in clause.__dict__.items():
                if key != "id" and not key.startswith("_"):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        self._session.add(clause)
        await self._session.flush()
        await self._session.refresh(clause)
        return clause


class PaperTemplateRuleRepository(BaseRepository[PaperTemplateRule]):
    def __init__(self, session: AsyncSession):
        super().__init__(session)

    async def list_enabled_by_template(self, template_id: str) -> list[PaperTemplateRule]:
        stmt = select(PaperTemplateRule).where(
            PaperTemplateRule.template_id == template_id,
            PaperTemplateRule.enabled == True,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_template(self, template_id: str) -> int:
        result = await self._session.execute(
            select(PaperTemplateRule).where(PaperTemplateRule.template_id == template_id)
        )
        rules = result.scalars().all()
        for rule in rules:
            await self._session.delete(rule)
        return len(rules)

    async def upsert_rule(self, rule: PaperTemplateRule) -> PaperTemplateRule:
        stmt = select(PaperTemplateRule).where(
            PaperTemplateRule.template_id == rule.template_id,
            PaperTemplateRule.rule_code == rule.rule_code,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            for key, value in rule.__dict__.items():
                if key != "id" and not key.startswith("_"):
                    setattr(existing, key, value)
            await self._session.flush()
            return existing
        self._session.add(rule)
        await self._session.flush()
        await self._session.refresh(rule)
        return rule
