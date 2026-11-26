import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import session as session_module
from app.enums import ActivityType
from app.schemas.activity import ActivityRead, ActivitySessionRead


async def test_get_db_yields_a_working_session_and_closes_it(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_async_engine(database_url)
    monkeypatch.setattr(
        session_module, "async_session_maker", async_sessionmaker(engine, expire_on_commit=False)
    )

    generator = session_module.get_db()
    session = await anext(generator)
    assert isinstance(session, AsyncSession)
    assert await session.scalar(text("SELECT 1")) == 1
    with pytest.raises(StopAsyncIteration):
        await anext(generator)

    assert session.in_transaction() is False
    await engine.dispose()


@pytest.mark.parametrize("schema", [ActivityRead, ActivitySessionRead])
def test_activity_type_labels_map_enums_and_keep_plain_strings(schema: type) -> None:
    common = {"id": uuid.uuid4(), "name": "x", "activity_id": uuid.uuid4()}
    extra = (
        {"time_spent_seconds": 10, "posted_at": "2026-01-01T00:00:00Z"}
        if schema is ActivitySessionRead
        else {}
    )

    from_enum = schema.model_validate({**common, **extra, "type": ActivityType.SELF_REGULATION})
    from_text = schema.model_validate({**common, **extra, "type": "breathing"})

    assert from_enum.type == "selfregulation"
    assert from_text.type == "breathing"
