"""
Battle and team related Pydantic schemas.
"""
from datetime import datetime, date
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from omninet.models.battle import BattleResult, SeasonStatus


class SeasonRestrictions(BaseModel):
    """Season restrictions schema."""

    allowed_stages: Optional[list[int]] = None
    allowed_attributes: Optional[list[str]] = None
    allowed_modules: Optional[list[str]] = None


class SeasonCreate(BaseModel):
    """Schema for creating a season."""

    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    start_date: date
    end_date: date
    restrictions: Optional[SeasonRestrictions] = None
    reward_multiplier: float = 1.0
    theme_name: Optional[str] = None
    banner_url: Optional[str] = None


class SeasonResponse(BaseModel):
    """Schema for season response."""

    id: UUID
    name: str
    description: Optional[str] = None
    start_date: date
    end_date: date
    status: SeasonStatus
    restrictions: Optional[dict] = None
    reward_multiplier: float
    theme_name: Optional[str] = None
    banner_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PetCreate(BaseModel):
    """Schema for creating a pet."""

    name: str = Field(..., min_length=1, max_length=200)
    module_name: str
    module_version: str
    pet_version: Optional[str] = None
    stage: int = Field(default=1, ge=1, le=7)
    level: int = Field(default=1, ge=1)
    atk_main: str
    atk_alt: Optional[str] = None
    atk_alt2: Optional[str] = None
    power: int = Field(default=0, ge=0)
    attribute: Optional[str] = None
    hp: int = Field(default=100, ge=1)
    star: int = Field(default=1, ge=1, le=5)
    critical_turn: int = Field(default=0, ge=0)
    extra_data: Optional[dict] = None


class PetResponse(BaseModel):
    """Schema for pet response."""

    id: UUID
    name: str
    module_name: str
    module_version: str
    pet_version: Optional[str] = None
    stage: int
    level: int
    atk_main: str
    atk_alt: Optional[str] = None
    atk_alt2: Optional[str] = None
    power: int
    attribute: Optional[str] = None
    hp: int
    star: int
    critical_turn: int
    extra_data: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamCreate(BaseModel):
    """Schema for creating a team."""

    name: Optional[str] = Field(None, max_length=100)
    pets: list[PetCreate] = Field(..., min_length=1, max_length=3)


class TeamResponse(BaseModel):
    """Schema for team response."""

    id: UUID
    name: Optional[str] = None
    score: int
    wins: int
    losses: int
    draws: int
    rewarded_coins: int
    reward_claimed: bool
    is_active: bool
    season_id: Optional[UUID] = None
    season_name: Optional[str] = None
    pets: list[PetResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamListResponse(BaseModel):
    """Simplified team list response."""

    id: UUID
    name: Optional[str] = None
    score: int
    wins: int
    losses: int
    draws: int
    pet_count: int
    reward_claimed: bool
    season_name: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class BattleResponse(BaseModel):
    """Schema for battle response."""

    id: UUID
    team1_id: UUID
    team2_id: UUID
    result: BattleResult
    winner_id: Optional[UUID] = None
    team1_score_change: int
    team2_score_change: int
    duration_seconds: int
    fought_at: datetime
    battle_log: Optional[dict] = None

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
    team_name: Optional[str] = None
    battles: list[BattleHistoryResponse]
    total_battles: int


class FindBattleResponse(BaseModel):
    """Response when finding a battle."""

    battle_found: bool
    message: str
    battle: Optional[BattleResponse] = None
    daily_battles_remaining: int


class ClaimRewardResponse(BaseModel):
    """Response when claiming rewards."""

    coins_claimed: int
    new_balance: int
    teams_processed: int
    message: str
