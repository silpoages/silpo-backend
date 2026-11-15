import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import Mood
from app.models.diary_entry import DiaryEntry
from app.models.mood_log import MoodLog
from app.schemas.diary_entry import DiaryCalendarDay, DiaryEntryCreate, DiaryMonthSummary
from app.services.achievement import AchievementService
from app.services.image_storage import (
    CONTENT_TYPES,
    ImageStorage,
    image_owner_id,
    new_image_key,
)


class DiaryEntryService:
    def __init__(self, db: AsyncSession, images: ImageStorage | None = None) -> None:
        self.db = db
        self.images = images

    @staticmethod
    def _visible(user_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
        return (
            DiaryEntry.user_id == user_id,
            DiaryEntry.enabled.is_(True),
            DiaryEntry.deleted_at.is_(None),
        )

    @staticmethod
    def _deleted(user_id: uuid.UUID) -> tuple[ColumnElement[bool], ...]:
        return (DiaryEntry.user_id == user_id, DiaryEntry.deleted_at.is_not(None))

    async def create(self, user_id: uuid.UUID, payload: DiaryEntryCreate) -> DiaryEntry:
        if payload.mood is not None and payload.mood_log_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Send mood or mood_log_id, not both",
            )

        entry_date = payload.entry_date or datetime.now(UTC).date()
        mood_log_id = payload.mood_log_id
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
        elif payload.mood is not None:
            # O formulário manda a emoção junto da data escolhida no calendário,
            # que pode não ser hoje. POST /mood-logs sempre grava o dia corrente.
            mood_log = MoodLog(user_id=user_id, mood=payload.mood, log_date=entry_date)
            self.db.add(mood_log)
            await self.db.flush()
            mood_log_id = mood_log.id

        image_url = await self._owned_image(user_id, payload.image_url)

        entry = DiaryEntry(
            user_id=user_id,
            mood_log_id=mood_log_id,
            entry_date=entry_date,
            note=payload.note,
            image_url=image_url,
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

    def _dated(
        self,
        user_id: uuid.UUID,
        entry_date: date | None,
        start_date: date | None,
        end_date: date | None,
    ) -> tuple[ColumnElement[bool], ...]:
        if start_date is not None and end_date is not None and start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="start_date must be on or before end_date",
            )

        filters = self._visible(user_id)
        if entry_date is not None:
            filters = (*filters, DiaryEntry.entry_date == entry_date)
        if start_date is not None:
            filters = (*filters, DiaryEntry.entry_date >= start_date)
        if end_date is not None:
            filters = (*filters, DiaryEntry.entry_date <= end_date)
        return filters

    async def list_entries(
        self,
        user_id: uuid.UUID,
        entry_date: date | None = None,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        page: int | None = None,
        page_size: int = 10,
    ) -> list[DiaryEntry]:
        query = (
            select(DiaryEntry)
            .where(*self._dated(user_id, entry_date, start_date, end_date))
            .order_by(DiaryEntry.entry_date.desc(), DiaryEntry.created_at.desc())
        )
        if page is not None:
            query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_entries(
        self,
        user_id: uuid.UUID,
        entry_date: date | None = None,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        total = await self.db.scalar(
            select(func.count(DiaryEntry.id)).where(
                *self._dated(user_id, entry_date, start_date, end_date)
            )
        )
        return int(total or 0)

    async def save_image(self, user_id: uuid.UUID, data: bytes, extension: str) -> str:
        if self.images is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
        key = new_image_key(user_id, extension)
        await self.images.save(key, data, CONTENT_TYPES[extension])
        return key

    async def _owned_image(self, user_id: uuid.UUID, image_url: str | None) -> str | None:
        if image_url is None:
            return None
        owner = image_owner_id(image_url)
        if owner is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="image_url must be an uploaded diary image",
            )
        if owner != user_id or self.images is None or not await self.images.exists(image_url):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
        return image_url

    async def delete(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
        entry = await self.get_by_id(user_id, entry_id)
        image_url = entry.image_url
        entry.enabled = False
        entry.deleted_at = datetime.now(UTC)
        await self.db.commit()
        if (
            image_url is not None
            and image_owner_id(image_url) == user_id
            and self.images is not None
        ):
            await self.images.delete(image_url)

    async def list_deleted(
        self, user_id: uuid.UUID, *, page: int = 1, page_size: int = 10
    ) -> list[DiaryEntry]:
        result = await self.db.execute(
            select(DiaryEntry)
            .where(*self._deleted(user_id))
            .order_by(DiaryEntry.deleted_at.desc(), DiaryEntry.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all())

    async def count_deleted(self, user_id: uuid.UUID) -> int:
        total = await self.db.scalar(
            select(func.count(DiaryEntry.id)).where(*self._deleted(user_id))
        )
        return int(total or 0)

    async def restore(self, user_id: uuid.UUID, entry_id: uuid.UUID) -> DiaryEntry:
        entry = await self.db.scalar(
            select(DiaryEntry).where(DiaryEntry.id == entry_id, *self._deleted(user_id))
        )
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Diary entry not found"
            )

        # A foto é removida do storage quando o registro é apagado; volta só o texto.
        if entry.image_url is not None and (
            self.images is None or not await self.images.exists(entry.image_url)
        ):
            entry.image_url = None
        entry.enabled = True
        entry.deleted_at = None
        await self.db.commit()
        await AchievementService(self.db).evaluate_after_action(user_id)
        return await self.get_by_id(user_id, entry.id)

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
        counts: dict[date, int] = {day: total for day, total in result.all()}

        mood_rows = await self.db.execute(
            select(MoodLog.log_date, MoodLog.mood)
            .where(
                MoodLog.user_id == user_id,
                MoodLog.log_date >= first,
                MoodLog.log_date < next_month,
            )
            .order_by(MoodLog.log_date, MoodLog.posted_at, MoodLog.id)
        )
        moods_by_day: dict[date, list[Mood]] = {}
        for day, mood in mood_rows.all():
            moods_by_day.setdefault(day, []).append(mood)

        days = [
            DiaryCalendarDay(
                entry_date=day,
                entries_count=counts.get(day, 0),
                moods=moods_by_day.get(day, []),
            )
            for day in sorted(set(counts) | set(moods_by_day))
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
