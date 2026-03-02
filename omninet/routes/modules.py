"""
Module management routes.
"""
from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from omninet.models.module import ModuleStatus
from omninet.routes.deps import CurrentUser, DbSession
from omninet.schemas.common import MessageResponse, PaginatedResponse
from omninet.schemas.module import (
    CategoryResponse,
    ContributorRequest,
    ContributorResponse,
    ModuleContributorsResponse,
    ModuleListResponse,
    ModulePublishRequest,
    ModulePublishResponse,
    ModuleResponse,
)
from omninet.services.module import ModuleService

router = APIRouter(prefix="/modules", tags=["Modules"])


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    db: DbSession,
):
    """Get all module categories."""
    module_service = ModuleService(db)
    categories = await module_service.get_categories()

    return [
        CategoryResponse(
            id=c.id,
            name=c.name,
            description=c.description,
            display_order=c.display_order,
        )
        for c in categories
    ]


@router.get("", response_model=PaginatedResponse[ModuleListResponse])
async def list_modules(
    db: DbSession,
    category_id: UUID | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List published modules with optional filters."""
    module_service = ModuleService(db)
    offset = (page - 1) * page_size

    modules, total = await module_service.list_modules(
        category_id=category_id,
        status=ModuleStatus.PUBLISHED,
        search=search,
        limit=page_size,
        offset=offset,
    )

    items = [
        ModuleListResponse(
            id=m.id,
            name=m.name,
            version=m.version,
            description=m.description,
            category_name=m.category.name if m.category else None,
            status=m.status,
            owner_nickname=m.owner.nickname if m.owner else "Unknown",
            download_count=m.download_count,
            updated_at=m.updated_at,
        )
        for m in modules
    ]

    return PaginatedResponse.create(items, total, page, page_size)


@router.get("/mine", response_model=list[ModuleResponse])
async def list_my_modules(
    current_user: CurrentUser,
    db: DbSession,
):
    """List modules owned by or contributed to by the current user."""
    module_service = ModuleService(db)
    modules = await module_service.get_user_modules(current_user.id)

    return [
        ModuleResponse(
            id=m.id,
            name=m.name,
            version=m.version,
            description=m.description,
            category=CategoryResponse(
                id=m.category.id,
                name=m.category.name,
                description=m.category.description,
                display_order=m.category.display_order,
            ) if m.category else None,
            status=m.status,
            owner_nickname=m.owner.nickname if m.owner else "Unknown",
            file_size=m.file_size,
            download_count=m.download_count,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )
        for m in modules
    ]


@router.get("/{module_id}", response_model=ModuleResponse)
async def get_module(
    module_id: UUID,
    db: DbSession,
):
    """Get module details by ID."""
    module_service = ModuleService(db)
    module = await module_service.get_by_id(module_id)

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    return ModuleResponse(
        id=module.id,
        name=module.name,
        version=module.version,
        description=module.description,
        category=CategoryResponse(
            id=module.category.id,
            name=module.category.name,
            description=module.category.description,
            display_order=module.category.display_order,
        ) if module.category else None,
        status=module.status,
        owner_nickname=module.owner.nickname if module.owner else "Unknown",
        file_size=module.file_size,
        download_count=module.download_count,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


@router.post("/check-publish", response_model=ModulePublishResponse)
async def check_publish_permission(
    data: ModulePublishRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Check if the user can publish a module with the given name."""
    module_service = ModuleService(db)
    result = await module_service.check_publish_permission(
        user=current_user,
        module_name=data.name,
        version=data.version,
    )

    return ModulePublishResponse(**result)


@router.post("/publish", response_model=ModuleResponse)
async def publish_module(
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
):
    """
    Publish or update a module.
    Upload a zip file containing the module data with a module.json file.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a zip archive",
        )

    # Read file content
    content = await file.read()
    if len(content) > 100 * 1024 * 1024:  # 100MB limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large (max 100MB)",
        )

    module_service = ModuleService(db)
    success, message, module = await module_service.publish_module(
        user=current_user,
        module_name=file.filename.replace(".zip", ""),
        zip_data=content,
    )

    if not success or not module:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    # Reload module with relationships
    module = await module_service.get_by_id(module.id)

    return ModuleResponse(
        id=module.id,
        name=module.name,
        version=module.version,
        description=module.description,
        category=CategoryResponse(
            id=module.category.id,
            name=module.category.name,
            description=module.category.description,
            display_order=module.category.display_order,
        ) if module.category else None,
        status=module.status,
        owner_nickname=module.owner.nickname if module.owner else "Unknown",
        file_size=module.file_size,
        download_count=module.download_count,
        created_at=module.created_at,
        updated_at=module.updated_at,
    )


@router.post("/{module_id}/unpublish", response_model=MessageResponse)
async def unpublish_module(
    module_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Unpublish a module (owner only)."""
    module_service = ModuleService(db)
    success, message = await module_service.unpublish_module(current_user, module_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return MessageResponse(message=message)


@router.get("/{module_id}/download")
async def download_module(
    module_id: UUID,
    db: DbSession,
):
    """Download a module's zip file."""
    module_service = ModuleService(db)
    result = await module_service.get_module_file(module_id)

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module file not found",
        )

    data, filename = result

    return StreamingResponse(
        BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/{module_id}/contributors", response_model=ModuleContributorsResponse)
async def get_module_contributors(
    module_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Get contributors for a module (owner only)."""
    module_service = ModuleService(db)
    module = await module_service.get_by_id(module_id)

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    if module.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can view contributors",
        )

    contributors = await module_service.get_contributors(module_id)

    return ModuleContributorsResponse(
        module_id=module.id,
        module_name=module.name,
        owner_nickname=module.owner.nickname,
        contributors=[
            ContributorResponse(
                user_id=c.user_id,
                nickname=c.user.nickname if c.user else "Unknown",
                can_publish=c.can_publish,
                added_at=c.added_at,
            )
            for c in contributors
        ],
    )


@router.post("/{module_id}/contributors", response_model=MessageResponse)
async def add_contributor(
    module_id: UUID,
    nickname: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Add a contributor to a module (owner only)."""
    module_service = ModuleService(db)
    success, message = await module_service.add_contributor(
        owner=current_user,
        module_id=module_id,
        contributor_nickname=nickname,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return MessageResponse(message=message)


@router.delete("/{module_id}/contributors/{nickname}", response_model=MessageResponse)
async def remove_contributor(
    module_id: UUID,
    nickname: str,
    current_user: CurrentUser,
    db: DbSession,
):
    """Remove a contributor from a module (owner only)."""
    module_service = ModuleService(db)
    success, message = await module_service.remove_contributor(
        owner=current_user,
        module_id=module_id,
        contributor_nickname=nickname,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return MessageResponse(message=message)


@router.put("/{module_id}/contributors", response_model=MessageResponse)
async def update_contributors(
    module_id: UUID,
    data: ContributorRequest,
    current_user: CurrentUser,
    db: DbSession,
):
    """Update the list of contributors for a module (owner only)."""
    module_service = ModuleService(db)
    success, message, invalid = await module_service.update_contributors(
        owner=current_user,
        module_id=module_id,
        contributor_nicknames=data.nicknames,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )

    return MessageResponse(message=message)
