"""
Module-related Pydantic schemas.
"""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from omninet.models.module import ModuleStatus


class CategoryResponse(BaseModel):
    """Schema for category response."""

    id: UUID
    name: str
    description: str | None = None
    display_order: int

    model_config = {"from_attributes": True}


class ModuleCreate(BaseModel):
    """Schema for creating a module."""

    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=50)
    description: str | None = None
    category_id: UUID | None = None


class ModuleUpdate(BaseModel):
    """Schema for updating a module."""

    description: str | None = None
    category_id: UUID | None = None


class ModulePublishRequest(BaseModel):
    """Request to check if module can be published."""

    name: str
    version: str


class ModulePublishResponse(BaseModel):
    """Response for publish check."""

    can_publish: bool
    is_new: bool
    is_update: bool
    message: str
    module_id: UUID | None = None


class ModuleResponse(BaseModel):
    """Schema for module response."""

    id: UUID
    name: str
    version: str
    description: str | None = None
    category: CategoryResponse | None = None
    status: ModuleStatus
    owner_nickname: str
    file_size: int
    download_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ModuleListResponse(BaseModel):
    """Schema for listing modules (simplified)."""

    id: UUID
    name: str
    version: str
    description: str | None = None
    category_name: str | None = None
    status: ModuleStatus
    owner_nickname: str
    download_count: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContributorRequest(BaseModel):
    """Request to add/remove contributors."""

    nicknames: list[str] = Field(..., max_length=50)


class ContributorResponse(BaseModel):
    """Response for contributor info."""

    user_id: UUID
    nickname: str
    can_publish: bool
    added_at: datetime

    model_config = {"from_attributes": True}


class ModuleContributorsResponse(BaseModel):
    """Response listing all contributors for a module."""

    module_id: UUID
    module_name: str
    owner_nickname: str
    contributors: list[ContributorResponse]
