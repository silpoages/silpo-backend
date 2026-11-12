import uuid

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_message import DailyMessage
from app.schemas.daily_message import DailyMessageCreate, DailyMessageUpdate


class DailyMessageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _base_filters(search: str | None) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [DailyMessage.deleted_at.is_(None)]
        term = search.strip() if search else ""
        if term:
            filters.append(DailyMessage.message.icontains(term, autoescape=True))
        return filters

    async def list_paginated(
        self, page: int, page_size: int, search: str | None, enabled: bool | None
    ) -> list[DailyMessage]:
        query = select(DailyMessage).where(*self._base_filters(search))
        if enabled is not None:
            query = query.where(DailyMessage.enabled.is_(enabled))
        result = await self.db.execute(
            query.order_by(DailyMessage.created_at.desc(), DailyMessage.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all())

    async def count_by_status(self, search: str | None) -> dict[str, int]:
        result = await self.db.execute(
            select(func.count(), func.count().filter(DailyMessage.enabled.is_(True)))
            .select_from(DailyMessage)
            .where(*self._base_filters(search))
        )
        total, enabled = result.one()
        return {"total": total, "enabled": enabled, "disabled": total - enabled}

    async def create(self, payload: DailyMessageCreate) -> DailyMessage:
        daily_message = DailyMessage(message=payload.message, enabled=payload.enabled)
        self.db.add(daily_message)
        await self.db.commit()
        await self.db.refresh(daily_message)
        return daily_message

    async def update(self, message_id: uuid.UUID, payload: DailyMessageUpdate) -> DailyMessage:
        daily_message = await self._get_or_404(message_id)
        for field, value in payload.model_dump(exclude_none=True).items():
            setattr(daily_message, field, value)
        await self.db.commit()
        await self.db.refresh(daily_message)
        return daily_message

    async def _get_or_404(self, message_id: uuid.UUID) -> DailyMessage:
        result = await self.db.execute(
            select(DailyMessage).where(
                DailyMessage.id == message_id,
                DailyMessage.deleted_at.is_(None),
            )
        )
        daily_message = result.scalar_one_or_none()
        if daily_message is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Daily message not found"
            )
        return daily_message
