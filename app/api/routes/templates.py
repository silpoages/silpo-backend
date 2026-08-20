import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_template_service
from app.schemas.template import TemplateCreate, TemplateRead, TemplateUpdate
from app.services.template import TemplateService

router = APIRouter(prefix="/templates", tags=["templates"])


@router.post("", response_model=TemplateRead, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate, service: TemplateService = Depends(get_template_service)
):
    return await service.create(payload)


@router.get("", response_model=list[TemplateRead])
async def list_templates(service: TemplateService = Depends(get_template_service)):
    return await service.list()


@router.get("/{template_id}", response_model=TemplateRead)
async def get_template(
    template_id: uuid.UUID, service: TemplateService = Depends(get_template_service)
):
    template = await service.get(template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return template


@router.patch("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: uuid.UUID,
    payload: TemplateUpdate,
    service: TemplateService = Depends(get_template_service),
):
    template = await service.get(template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return await service.update(template, payload)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID, service: TemplateService = Depends(get_template_service)
) -> None:
    template = await service.get(template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    await service.delete(template)
