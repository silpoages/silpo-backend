import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, payload: ItemCreate) -> Item:
        item = Item(**payload.model_dump())
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list(self) -> list[Item]:
        result = await self.db.execute(select(Item).order_by(Item.created_at))
        return list(result.scalars().all())

    async def get(self, item_id: uuid.UUID) -> Item | None:
        return await self.db.get(Item, item_id)

    async def update(self, item: Item, payload: ItemUpdate) -> Item:
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(item, field, value)

        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def delete(self, item: Item) -> None:
        await self.db.delete(item)
        await self.db.commit()
