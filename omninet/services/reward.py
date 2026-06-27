"""
Reward service — validates and grants coin rewards for in-game events.

Security model
--------------
The client sends a plain idempotency key constructed from stable event context
(module name, pet name, timestamp, etc.).  The server stores every claimed key
per user and rejects any duplicate, preventing the same event from being
rewarded twice.  There is no shared secret: because the game is open source and
some builds ship as plain Python, client-side secrets would provide no real
protection.  The deduplication alone is sufficient to prevent trivial farming.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.config import settings
from omninet.models.reward import RewardClaim
from omninet.models.user import User

VALID_EVENT_TYPES = frozenset({
    "unlock", "evolution", "new_pet", "adventure", "area_clear",
})


def _coin_value(event_type: str) -> int:
    return {
        "unlock":     settings.reward_coins_unlock,
        "evolution":  settings.reward_coins_evolution,
        "new_pet":    settings.reward_coins_new_pet,
        "adventure":  settings.reward_coins_adventure,
        "area_clear": settings.reward_coins_area_clear,
    }[event_type]


class RewardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _key_already_used(self, user_id, key: str) -> bool:
        result = await self.db.execute(
            select(RewardClaim).where(
                RewardClaim.user_id == user_id,
                RewardClaim.idempotency_key == key,
            )
        )
        return result.scalar_one_or_none() is not None

    async def claim_reward(
        self,
        user: User,
        event_type: str,
        idempotency_key: str,
    ) -> tuple[bool, int, str]:
        """
        Validate and apply a coin reward.

        Returns:
            (success, coins_awarded, message)
        """
        if event_type not in VALID_EVENT_TYPES:
            return False, 0, "Unknown event type"

        if not idempotency_key or len(idempotency_key) > 256:
            return False, 0, "Invalid idempotency key"

        if await self._key_already_used(user.id, idempotency_key):
            return False, 0, "Already claimed"

        coins = _coin_value(event_type)

        self.db.add(RewardClaim(
            user_id=user.id,
            idempotency_key=idempotency_key,
            event_type=event_type,
            coins_awarded=coins,
        ))

        user.coins += coins
        await self.db.flush()

        return True, coins, f"Awarded {coins} coins"
