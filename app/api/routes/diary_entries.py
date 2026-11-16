import re
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.api.deps import get_current_user, get_diary_entry_service
from app.models.diary_entry import DiaryEntry
from app.models.user import User
from app.schemas.diary_entry import (
    DiaryDeletedEntryListResponse,
    DiaryDeletedEntryRead,
    DiaryEntryCreate,
    DiaryEntryListResponse,
    DiaryEntryRead,
    DiaryImageRead,
    DiaryMonthSummary,
)
from app.services.diary_entry import DiaryEntryService
from app.services.image_storage import (
    LocalImageStorage,
    S3ImageStorage,
    content_type_for_key,
    get_image_storage,
    image_owner_id,
)
from app.services.image_validation import read_validated_image

router = APIRouter(prefix="/diary-entries", tags=["diary-entries"])

_MONTH = re.compile(r"^(\d{4})-(\d{2})$")


def _parse_month(month: str) -> tuple[int, int]:
    match = _MONTH.fullmatch(month)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="month must be YYYY-MM"
        )
    return int(match.group(1)), int(match.group(2))


@router.get("", response_model=DiaryEntryListResponse)
async def list_diary_entries(
    start_date: date | None = None,
    end_date: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryEntryListResponse:
    items = await service.list_entries(
        current_user.id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    total = await service.count_entries(current_user.id, start_date=start_date, end_date=end_date)
    return DiaryEntryListResponse(
        items=[DiaryEntryRead.model_validate(entry) for entry in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=DiaryEntryRead, status_code=status.HTTP_201_CREATED)
async def create_diary_entry(
    payload: DiaryEntryCreate,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryEntry:
    return await service.create(current_user.id, payload)


@router.post("/images", response_model=DiaryImageRead, status_code=status.HTTP_201_CREATED)
async def upload_diary_image(
    file: Annotated[UploadFile, File()],
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryImageRead:
    data, extension = await read_validated_image(file)
    image_url = await service.save_image(current_user.id, data, extension)
    return DiaryImageRead(image_url=image_url)


@router.get("/images/{key:path}", response_model=None)
async def get_diary_image(
    key: str,
    current_user: User = Depends(get_current_user),
    storage: LocalImageStorage | S3ImageStorage = Depends(get_image_storage),
) -> Response:
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    if image_owner_id(key) != current_user.id:
        raise not_found

    if isinstance(storage, S3ImageStorage):
        # Entregue pela própria API, não por redirecionamento a um link temporário do S3: o app
        # pede a foto com o token no Authorization, e seguir o redirecionamento com o token faz o
        # S3 recusar ("Only one auth mechanism allowed"); no navegador, o redirecionamento ainda
        # exigiria CORS no bucket. As fotos têm centenas de KB, então passar pela API não pesa.
        data = await storage.read(key)
        if data is None:
            raise not_found
        return Response(
            content=data,
            media_type=content_type_for_key(key),
            # Só o próprio usuário pode ver: nada de cache compartilhado (CloudFront, proxies).
            headers={"Cache-Control": "private, max-age=300"},
        )
    if isinstance(storage, LocalImageStorage) and await storage.exists(key):
        return FileResponse(storage.path_for(key), media_type=content_type_for_key(key))
    raise not_found


@router.get("/calendar", response_model=DiaryMonthSummary)
async def get_diary_calendar(
    month: str,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryMonthSummary:
    year, month_number = _parse_month(month)
    return await service.get_month_summary(current_user.id, year, month_number)


# Antes de `/{entry_id}`: senão "deleted" seria lido como id.
@router.get("/deleted", response_model=DiaryDeletedEntryListResponse)
async def list_deleted_diary_entries(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryDeletedEntryListResponse:
    items = await service.list_deleted(current_user.id, page=page, page_size=page_size)
    total = await service.count_deleted(current_user.id)
    return DiaryDeletedEntryListResponse(
        items=[DiaryDeletedEntryRead.model_validate(entry) for entry in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{entry_id}/restore", response_model=DiaryEntryRead)
async def restore_diary_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryEntry:
    return await service.restore(current_user.id, entry_id)


@router.get("/{entry_id}", response_model=DiaryEntryRead)
async def get_diary_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> DiaryEntry:
    return await service.get_by_id(current_user.id, entry_id)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diary_entry(
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DiaryEntryService = Depends(get_diary_entry_service),
) -> None:
    await service.delete(current_user.id, entry_id)
