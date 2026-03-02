"""
Battle and team related Pydantic schemas.
"""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from omninet.models.battle import BattleResult, SeasonStatus


class SeasonRestrictions(BaseModel):
    """Season restrictions schema."""

    allowed_stages: list[int] | None = None
    allowed_attributes: list[str] | None = None
    allowed_modules: list[str] | None = None


class SeasonCreate(BaseModel):
    """Schema for creating a season."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    start_date: date
    end_date: date
    restrictions: SeasonRestrictions | None = None
    reward_multiplier: float = 1.0
    theme_name: str | None = None
    banner_url: str | None = None


class SeasonResponse(BaseModel):
    """Schema for season response."""

    id: UUID
    name: str
    description: str | None = None
    start_date: date
    end_date: date
    status: SeasonStatus
    restrictions: dict | None = None
    reward_multiplier: float
    theme_name: str | None = None
    banner_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PetCreate(BaseModel):
    """Schema for creating a pet."""

    name: str = Field(..., min_length=1, max_length=200)
    module_name: str
    module_version: str
    pet_version: str | None = None
    stage: int = Field(default=1, ge=1, le=7)
    level: int = Field(default=1, ge=1)
    atk_main: str
    atk_alt: str | None = None
    atk_alt2: str | None = None
    power: int = Field(default=0, ge=0)
    attribute: str | None = None
    hp: int = Field(default=100, ge=1)
    star: int = Field(default=1, ge=1, le=5)
    critical_turn: int = Field(default=0, ge=0)
    extra_data: dict | None = None


class PetResponse(BaseModel):
    """Schema for pet response."""

    id: UUID
    name: str
    module_name: str
    module_version: str
    pet_version: str | None = None
    stage: int
    level: int
    atk_main: str
    atk_alt: str | None = None
    atk_alt2: str | None = None
    power: int
    attribute: str | None = None
    hp: int
    star: int
    critical_turn: int
    extra_data: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    """Schema for creating a team."""

    name: str | None = Field(None, max_length=100)
    pets: list[PetCreate] = Field(..., min_length=1, max_length=3)


class TeamResponse(BaseModel):
    """Schema for team response."""

    id: UUID
    name: str | None = None
    score: int
    wins: int
    losses: int
    draws: int
    rewarded_coins: int
    reward_claimed: bool
    is_active: bool
    season_id: UUID | None = None
    season_name: str | None = None
    pets: list[PetResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamListResponse(BaseModel):
    """Simplified team list response."""

    id: UUID
    name: str | None = None
    score: int
    wins: int
    losses: int
    draws: int
    pet_count: int
    reward_claimed: bool
    season_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BattleResponse(BaseModel):
    """Schema for battle response."""

    id: UUID
    team1_id: UUID
    team2_id: UUID
    result: BattleResult
    winner_id: UUID | None = None
    team1_score_change: int
    team2_score_change: int
    duration_seconds: int
    fought_at: datetime
    battle_log: dict | None = None

    model_config = {"from_attributes": True}


class BattleHistoryResponse(BaseModel):
    """Simplified battle history entry."""

    id: UUID
    opponent_team_id: UUID
    opponent_nickname: str
    won: bool
    score_change: int
    fought_at: datetime

    model_config = {"from_attributes": True}


class BattleHistoryListResponse(BaseModel):
    """List of battle history entries."""

    team_id: UUID
    team_name: str | None = None
    battles: list[BattleHistoryResponse]
    total_battles: int


class FindBattleResponse(BaseModel):
    """Response when finding a battle."""

    battle_found: bool
    message: str
    battle: BattleResponse | None = None
    daily_battles_remaining: int


class ClaimRewardResponse(BaseModel):
    """Response when claiming rewards."""

    coins_claimed: int
    new_balance: int
    teams_processed: int
    message: str
