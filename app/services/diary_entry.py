import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.diary_entry import DiaryEntry
from app.models.mood_log import MoodLog
from app.schemas.diary_entry import DiaryCalendarDay, DiaryEntryCreate, DiaryMonthSummary
from app.services.achievement import AchievementService


class DiaryEntryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _visible(user_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
        return (
            DiaryEntry.user_id == user_id,
            DiaryEntry.enabled.is_(True),
            DiaryEntry.deleted_at.is_(None),
        )

    async def create(self, user_id: uuid.UUID, payload: DiaryEntryCreate) -> DiaryEntry:
        if payload.mood_log_id is not None:
            owned = await self.db.scalar(
                select(MoodLog.id).where(
                    MoodLog.id == payload.mood_log_id, MoodLog.user_id == user_id
                )
            )
            if owned is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Mood log not found"
                )

        entry = DiaryEntry(
            user_id=user_id,
            mood_log_id=payload.mood_log_id,
            entry_date=payload.entry_date or datetime.now(UTC).date(),
            note=payload.note,
            image_url=payload.image_url,
        )
        self.db.add(entry)
        await self.db.commit()
        await AchievementService(self.db).evaluate_after_action(user_id)
        return await self.get_by_id(user_id, entry.id)

    async def get_by_id(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> DiaryEntry:
        entry = await self.db.scalar(
            select(DiaryEntry)
            .where(DiaryEntry.id == entry_id, *self._visible(user_id))
            .execution_options(populate_existing=True)
        )
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Diary entry not found"
            )
        return entry

    async def list_entries(
        self, user_id: uuid.UUID, entry_date: date | None = None
    ) -> list[DiaryEntry]:
        query = select(DiaryEntry).where(*self._visible(user_id))
        if entry_date is not None:
            query = query.where(DiaryEntry.entry_date == entry_date)

        result = await self.db.execute(
            query.order_by(DiaryEntry.entry_date.desc(), DiaryEntry.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
        entry = await self.get_by_id(user_id, entry_id)
        entry.enabled = False
        entry.deleted_at = datetime.now(UTC)
        await self.db.commit()

    async def get_month_summary(
        self, user_id: uuid.UUID, year: int, month: int
    ) -> DiaryMonthSummary:
        try:
            first = date(year, month, 1)
            next_month = (first + timedelta(days=32)).replace(day=1)
        except (ValueError, OverflowError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid year or month"
            ) from None

        result = await self.db.execute(
            select(DiaryEntry.entry_date, func.count(DiaryEntry.id))
            .where(
                *self._visible(user_id),
                DiaryEntry.entry_date >= first,
                DiaryEntry.entry_date < next_month,
            )
            .group_by(DiaryEntry.entry_date)
            .order_by(DiaryEntry.entry_date)
        )
        days = [
            DiaryCalendarDay(entry_date=day, entries_count=count) for day, count in result.all()
        ]
        return DiaryMonthSummary(year=year, month=month, days=days)

    async def list_mood_logs(
        self, user_id: uuid.UUID, log_date: date | None = None
    ) -> list[MoodLog]:
        query = select(MoodLog).where(MoodLog.user_id == user_id)
        if log_date is not None:
            query = query.where(MoodLog.log_date == log_date)

        result = await self.db.execute(query.order_by(MoodLog.posted_at.desc()))
        return list(result.scalars().all())
