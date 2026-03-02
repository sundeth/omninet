"""
User management routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from omninet.routes.deps import CurrentUser, DbSession
from omninet.schemas.common import MessageResponse
from omninet.schemas.user import DeviceResponse, UserResponse, UserUpdate
from omninet.services.device import DeviceService
from omninet.services.user import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: CurrentUser,
):
    """Get the current user's profile."""
    return UserResponse(
        id=current_user.id,
        nickname=current_user.nickname,
        email=current_user.email,
        type_name=current_user.user_type.name if current_user.user_type else "Standard",
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        coins=current_user.coins,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        last_login_at=current_user.last_login_at,
    )


@router.patch("/me", response_model=UserResponse)
async def update_current_user(
    data: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
):
    """Update the current user's profile."""
    user_service = UserService(db)

    # Check if new nickname is taken
    if data.nickname and data.nickname.lower() != current_user.nickname.lower():
        if await user_service.nickname_exists(data.nickname):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nickname is already taken",
            )

    user = await user_service.update_user(current_user, nickname=data.nickname)

    return UserResponse(
        id=user.id,
        nickname=user.nickname,
        email=user.email,
        type_name=user.user_type.name if user.user_type else "Standard",
        is_active=user.is_active,
        is_verified=user.is_verified,
        coins=user.coins,
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=user.last_login_at,
    )


@router.get("/me/devices", response_model=list[DeviceResponse])
async def get_user_devices(
    current_user: CurrentUser,
    db: DbSession,
):
    """Get all devices for the current user."""
    device_service = DeviceService(db)
    devices = await device_service.get_user_devices(current_user.id)

    return [
        DeviceResponse(
            id=d.id,
            device_name=d.device_name,
            device_type=d.device_type,
            is_active=d.is_active,
            created_at=d.created_at,
            last_used_at=d.last_used_at,
        )
        for d in devices
    ]


@router.delete("/me/devices/{device_id}", response_model=MessageResponse)
async def delete_user_device(
    device_id: UUID,
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete a specific device."""
    device_service = DeviceService(db)
    device = await device_service.get_by_id(device_id)

    if not device or device.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )

    await device_service.delete_device(device_id)

    return MessageResponse(message="Device deleted successfully")


@router.delete("/me/devices", response_model=MessageResponse)
async def delete_all_user_devices(
    current_user: CurrentUser,
    db: DbSession,
):
    """Delete all devices for the current user."""
    device_service = DeviceService(db)
    count = await device_service.delete_all_user_devices(current_user.id)

    return MessageResponse(message=f"Deleted {count} device(s)")


@router.get("/{nickname}", response_model=UserResponse)
async def get_user_by_nickname(
    nickname: str,
    db: DbSession,
):
    """Get a user's public profile by nickname."""
    user_service = UserService(db)
    user = await user_service.get_by_nickname(nickname)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Return limited public info
    return UserResponse(
        id=user.id,
        nickname=user.nickname,
        email="",  # Hide email in public profile
        type_name=user.user_type.name if user.user_type else "Standard",
        is_active=user.is_active,
        is_verified=user.is_verified,
        coins=0,  # Hide coins in public profile
        created_at=user.created_at,
        updated_at=user.updated_at,
        last_login_at=None,  # Hide last login in public profile
    )
