"""
User-related Pydantic schemas.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreate(BaseModel):
    """Schema for user registration."""

    nickname: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str) -> str:
        """Validate nickname contains only allowed characters."""
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError(
                "Nickname can only contain letters, numbers, underscores, and hyphens"
            )
        return v


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    nickname: Optional[str] = Field(None, min_length=3, max_length=100)


class UserResponse(BaseModel):
    """Schema for user response."""

    id: UUID
    nickname: str
    email: str
    type_name: str
    is_active: bool
    is_verified: bool
    coins: int
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserPublicResponse(BaseModel):
    """Public user info (visible to other users)."""

    id: UUID
    nickname: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DeviceResponse(BaseModel):
    """Schema for device response."""

    id: UUID
    device_name: Optional[str] = None
    device_type: str
    is_active: bool
    created_at: datetime
    last_used_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DeviceKeyResponse(BaseModel):
    """Response containing the secret key for auto-login."""

    secret_key: str
    device_id: UUID
    message: str = "Device registered successfully"


class VerificationRequest(BaseModel):
    """Schema for email verification."""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    clear_devices: bool = False


class PairingCodeResponse(BaseModel):
    """Response containing pairing code for game device linking."""

    code: str
    expires_in_seconds: int = 300  # 5 minutes


class PairingValidateRequest(BaseModel):
    """Request to validate pairing code from game."""

    code: str = Field(..., min_length=4, max_length=4)


class PasswordResetRequest(BaseModel):
    """Request for password reset."""

    email: EmailStr


class PasswordResetConfirm(BaseModel):
    """Confirm password reset with code and new password."""

    email: EmailStr
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=6, max_length=100)


class CoinBalanceResponse(BaseModel):
    """Response with user's coin balance."""

    coins: int
    nickname: str
