"""
Contribution points, credited server to server by the Digimon Database.

    POST /api/v1/internal/contribution-points/credit
    X-Service-Token: <settings.contribution_service_token>
    {"credits": [{"key": "dbgather:DMC:812", "email": "a@b.c", "points": 2,
                  "reason": "data_needed", "details": {...}}]}

Each credit is idempotent by its key: sending it again answers "duplicate"
and changes nothing, so the sender can retry freely. An email no account has
is kept ("pending") and claimed when that account next reads its balance.
"""
import hmac
import re

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from omninet.config import settings
from omninet.routes.deps import DbSession
from omninet.services.contribution import CREDITED, DUPLICATE, PENDING, ContributionService

router = APIRouter(prefix="/internal/contribution-points", tags=["contribution points"])

#: The most credits one request may carry (a backfill sends them in batches).
MAX_CREDITS_PER_REQUEST = 500

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


class ContributionCreditIn(BaseModel):
    key: str = Field(..., min_length=1, max_length=256)
    email: str = Field(..., min_length=3, max_length=254)
    points: int = Field(..., ge=1)
    reason: str | None = Field(None, max_length=64)
    details: dict | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not _EMAIL.match(value):
            raise ValueError("not an email address")
        return value


class ContributionCreditBatch(BaseModel):
    source: str = Field("digimon-database", min_length=1, max_length=64)
    credits: list[ContributionCreditIn] = Field(..., min_length=1,
                                                max_length=MAX_CREDITS_PER_REQUEST)


class ContributionCreditResult(BaseModel):
    key: str
    status: str          # credited | pending | duplicate
    points: int


class ContributionCreditResponse(BaseModel):
    results: list[ContributionCreditResult]
    credited: int
    pending: int
    duplicate: int


def _require_service_token(token: str | None) -> None:
    expected = settings.contribution_service_token
    if not expected:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Contribution points are not configured on this server")
    if not token or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Invalid service token")


@router.post("/credit", response_model=ContributionCreditResponse)
async def credit_contribution_points(
    body: ContributionCreditBatch,
    db: DbSession,
    x_service_token: str | None = Header(None),
) -> ContributionCreditResponse:
    """Credit contribution points by email, once per key."""
    _require_service_token(x_service_token)
    limit = settings.contribution_max_points_per_credit
    for item in body.credits:
        if item.points > limit:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail=f"{item.key}: at most {limit} points per credit")

    service = ContributionService(db)
    results = []
    counts = {CREDITED: 0, PENDING: 0, DUPLICATE: 0}
    for item in body.credits:
        outcome, row = await service.credit(
            key=item.key, email=item.email, points=item.points,
            source=body.source, reason=item.reason, details=item.details,
        )
        counts[outcome] += 1
        results.append(ContributionCreditResult(key=item.key, status=outcome, points=row.points))
    await db.commit()
    return ContributionCreditResponse(results=results, credited=counts[CREDITED],
                                      pending=counts[PENDING], duplicate=counts[DUPLICATE])
