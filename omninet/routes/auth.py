"""
Authentication routes.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status

from omninet.database import get_db
from omninet.routes.deps import DbSession, CurrentUser, get_client_ip
from omninet.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    VerificationRequest,
    DeviceKeyResponse,
    PairingCodeResponse,
    PairingValidateRequest,
    PasswordResetRequest,
    PasswordResetConfirm,
    CoinBalanceResponse,
)
from omninet.schemas.common import MessageResponse, SuccessResponse
from omninet.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=MessageResponse)
async def register(
    request: Request,
    data: UserCreate,
    db: DbSession,
):
    """
    Register a new user account.
    Sends a verification code to the provided email.
    """
    auth_service = AuthService(db)
    success, message, user = await auth_service.register_user(
        nickname=data.nickname,
        email=data.email,
        password=data.password,
        ip_address=get_client_ip(request),
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return MessageResponse(message=message)


@router.post("/verify-registration", response_model=DeviceKeyResponse)
async def verify_registration(
    request: Request,
    data: VerificationRequest,
    db: DbSession,
):
    """
    Verify registration with the code sent to email.
    Returns a device key for auto-login.
    """
    auth_service = AuthService(db)
    success, message, secret_key, device_id = await auth_service.verify_registration(
        email=data.email,
        code=data.code,
        ip_address=get_client_ip(request),
    )

    if not success or not secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return DeviceKeyResponse(
        secret_key=secret_key,
        device_id=device_id,
        message=message,
    )


@router.post("/login", response_model=MessageResponse)
async def login(
    request: Request,
    data: UserLogin,
    db: DbSession,
):
    """
    Login with email and password.
    Sends a verification code to the email.
    """
    auth_service = AuthService(db)
    success, message, user = await auth_service.login(
        email=data.email,
        password=data.password,
        ip_address=get_client_ip(request),
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)

    return MessageResponse(message=message)


@router.post("/verify-login", response_model=DeviceKeyResponse)
async def verify_login(
    request: Request,
    data: VerificationRequest,
    db: DbSession,
):
    """
    Verify login with the code sent to email.
    Optionally clears all existing devices.
    Returns a device key for auto-login.
    """
    auth_service = AuthService(db)
    success, message, secret_key, device_id = await auth_service.verify_login(
        email=data.email,
        code=data.code,
        clear_devices=data.clear_devices,
        ip_address=get_client_ip(request),
    )

    if not success or not secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return DeviceKeyResponse(
        secret_key=secret_key,
        device_id=device_id,
        message=message,
    )


@router.post("/validate-device", response_model=UserResponse)
async def validate_device(
    current_user: CurrentUser,
):
    """
    Validate a device key and return user info.
    Used for auto-login.
    """
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


@router.post("/generate-pairing-code", response_model=PairingCodeResponse)
async def generate_pairing_code(
    current_user: CurrentUser,
    db: DbSession,
):
    """
    Generate a pairing code for linking a game device.
    The code is valid for 5 minutes.
    """
    auth_service = AuthService(db)
    code = await auth_service.generate_game_pairing_code(current_user)

    return PairingCodeResponse(code=code, expires_in_seconds=300)


@router.post("/validate-pairing-code", response_model=DeviceKeyResponse)
async def validate_pairing_code(
    request: Request,
    data: PairingValidateRequest,
    db: DbSession,
):
    """
    Validate a pairing code and link a game device.
    Returns a device key for auto-login.
    """
    auth_service = AuthService(db)
    success, message, secret_key, device_id = await auth_service.validate_game_pairing(
        code=data.code,
        ip_address=get_client_ip(request),
    )

    if not success or not secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return DeviceKeyResponse(
        secret_key=secret_key,
        device_id=device_id,
        message=message,
    )


@router.post("/resend-code", response_model=MessageResponse)
async def resend_verification_code(
    email: str,
    db: DbSession,
):
    """Resend verification code to email."""
    auth_service = AuthService(db)
    success, message = await auth_service.resend_verification_code(email)

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return MessageResponse(message=message)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    data: PasswordResetRequest,
    db: DbSession,
):
    """Request a password reset code."""
    auth_service = AuthService(db)
    success, message = await auth_service.request_password_reset(data.email)

    # Always return success to not reveal if email exists
    return MessageResponse(message=message)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    request: Request,
    data: PasswordResetConfirm,
    db: DbSession,
):
    """Reset password with verification code."""
    auth_service = AuthService(db)
    success, message = await auth_service.reset_password(
        email=data.email,
        code=data.code,
        new_password=data.new_password,
        ip_address=get_client_ip(request),
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return MessageResponse(message=message)


@router.get("/coins", response_model=CoinBalanceResponse)
async def get_coin_balance(
    current_user: CurrentUser,
):
    """Get the current user's coin balance."""
    return CoinBalanceResponse(
        coins=current_user.coins,
        nickname=current_user.nickname,
    )
