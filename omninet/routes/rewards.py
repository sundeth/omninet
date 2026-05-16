"""
Reward endpoints — in-game coin event claims.
"""
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from omninet.routes.deps import CurrentUser, DbSession
from omninet.services.reward import RewardService

router = APIRouter(prefix="/rewards", tags=["rewards"])


class RewardClaimRequest(BaseModel):
    event_type: str
    idempotency_key: str
    timestamp: int
    signature: str


class RewardClaimResponse(BaseModel):
    success: bool
    coins_awarded: int
    total_coins: int
    message: str


@router.post("/claim", response_model=RewardClaimResponse)
async def claim_reward(
    body: RewardClaimRequest,
    current_user: CurrentUser,
    db: DbSession,
    x_device_key: Annotated[str | None, Header()] = None,
) -> RewardClaimResponse:
    """
    Grant coins for an in-game event.

    The request must carry a valid HMAC-SHA256 signature computed from
    the device key, event type, idempotency key and timestamp.  The server
    rejects stale timestamps (>5 min) and duplicate idempotency keys.
    """
    if not x_device_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device key required")

    service = RewardService(db)
    success, coins, message = await service.claim_reward(
        user=current_user,
        device_key=x_device_key,
        event_type=body.event_type,
        idempotency_key=body.idempotency_key,
        timestamp=body.timestamp,
        signature=body.signature,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return RewardClaimResponse(
        success=True,
        coins_awarded=coins,
        total_coins=current_user.coins,
        message=message,
    )
