"""
Reward endpoints — in-game coin event claims.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from omninet.routes.deps import CurrentUser, DbSession
from omninet.services.reward import RewardService

router = APIRouter(prefix="/rewards", tags=["rewards"])


class RewardClaimRequest(BaseModel):
    event_type: str
    idempotency_key: str


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
) -> RewardClaimResponse:
    """
    Grant coins for an in-game event.

    The client sends a stable idempotency key derived from the event context
    (module name, pet name, timestamp, etc.).  The server rejects any key that
    has already been used by this player, preventing duplicate rewards.
    """
    service = RewardService(db)
    success, coins, message = await service.claim_reward(
        user=current_user,
        event_type=body.event_type,
        idempotency_key=body.idempotency_key,
    )

    if not success:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    return RewardClaimResponse(
        success=True,
        coins_awarded=coins,
        total_coins=current_user.coins,
        message=message,
    )
