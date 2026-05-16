"""
Reward service — validates HMAC-signed reward claims and grants coins.

Security model
--------------
The game client and server share a secret (REWARD_SIGNING_SECRET in .env,
mirrored as a constant in the game binary).  For every in-game reward event
the client builds:

    idempotency_key = SHA-256( device_key + event_type + context + 5-min-window )
    message         = "{device_key}|{event_type}|{idempotency_key}|{timestamp}"
    signature       = HMAC-SHA256( secret, message )

The server verifies the signature, checks the timestamp is within ±5 min,
and rejects any idempotency_key that has been used before.  This blocks:

  * External API calls (no valid signature without the shared secret)
  * Replay attacks (idempotency_key is unique per 5-min window)
  * Rapid spamming (same context within the window = same key = deduped)
"""
import hashlib
import hmac
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omninet.config import settings
from omninet.models.reward import RewardClaim
from omninet.models.user import User

VALID_EVENT_TYPES = frozenset({"unlock", "evolution", "new_pet", "adventure"})

MAX_CLOCK_SKEW_SECONDS = 300  # ±5 minutes


def _coin_value(event_type: str) -> int:
    return {
        "unlock": settings.reward_coins_unlock,
        "evolution": settings.reward_coins_evolution,
        "new_pet": settings.reward_coins_new_pet,
        "adventure": settings.reward_coins_adventure,
    }[event_type]


class RewardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Signature validation
    # ------------------------------------------------------------------

    def verify_signature(
        self,
        device_key: str,
        event_type: str,
        idempotency_key: str,
        timestamp: int,
        signature: str,
    ) -> bool:
        """Return True iff the HMAC signature is valid and the timestamp is fresh."""
        if abs(time.time() - timestamp) > MAX_CLOCK_SKEW_SECONDS:
            return False
        message = f"{device_key}|{event_type}|{idempotency_key}|{timestamp}"
        expected = hmac.new(
            settings.reward_signing_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # Idempotency check
    # ------------------------------------------------------------------

    async def _key_already_used(self, key: str) -> bool:
        result = await self.db.execute(
            select(RewardClaim).where(RewardClaim.idempotency_key == key)
        )
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Claim
    # ------------------------------------------------------------------

    async def claim_reward(
        self,
        user: User,
        device_key: str,
        event_type: str,
        idempotency_key: str,
        timestamp: int,
        signature: str,
    ) -> tuple[bool, int, str]:
        """
        Validate and apply a coin reward.

        Returns:
            (success, coins_awarded, message)
        """
        if event_type not in VALID_EVENT_TYPES:
            return False, 0, "Unknown event type"

        if not self.verify_signature(device_key, event_type, idempotency_key, timestamp, signature):
            return False, 0, "Invalid or expired signature"

        if await self._key_already_used(idempotency_key):
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
