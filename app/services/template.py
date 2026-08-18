import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateUpdate


class TemplateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: TemplateCreate) -> Template:
        template = Template(**payload.model_dump())
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def list(self) -> list[Template]:
        result = await self.db.execute(select(Template).order_by(Template.created_at))
        return list(result.scalars().all())

    async def get(self, template_id: uuid.UUID) -> Template | None:
        return await self.db.get(Template, template_id)

    async def update(self, template: Template, payload: TemplateUpdate) -> Template:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(template, field, value)

        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def delete(self, template: Template) -> None:
        await self.db.delete(template)
        await self.db.commit()
