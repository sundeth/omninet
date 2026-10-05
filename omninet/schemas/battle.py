"""
Battle and team related Pydantic schemas.
"""
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from omninet.models.battle import BattleResult, SeasonStatus


class SeasonRestrictions(BaseModel):
    """Season restrictions schema.

    Attributes may be names (Vaccine, Data, Virus, Free) or the Va/Da/Vi
    codes monster.json uses.
    """

    allowed_stages: list[int] | None = None
    allowed_attributes: list[str] | None = None
    allowed_modules: list[str] | None = None


class SeasonConfig(BaseModel):
    """Per-season battle settings; unset keys use the server defaults."""

    attacks_per_day: int | None = Field(None, ge=0)
    charge: int | Literal["random"] | None = None
    win_score: int | None = None
    loss_score: int | None = None
    draw_score: int | None = None
    participation_coins: int | None = Field(None, ge=0)


class SeasonCreate(BaseModel):
    """Schema for scheduling a season (admin)."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    restrictions: SeasonRestrictions | None = None
    config: SeasonConfig | None = None
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
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: SeasonStatus
    restrictions: dict | None = None
    # Effective battle settings (server defaults + the season's overrides)
    config: dict | None = None
    runtime_version: str | None = None
    reward_multiplier: float
    theme_name: str | None = None
    banner_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PetCreate(BaseModel):
    """One Digimon of a team upload.

    Only the species identity and the care status are read: stage,
    attribute, power, HP and attacks come from the server's module data.
    Fields older clients sent (stage, power, ...) are accepted and ignored.
    """

    name: str = Field(..., min_length=1, max_length=200)
    module_name: str = Field(..., min_length=1, max_length=200)
    module_version: str | None = None
    pet_version: int | str | None = None
    status: dict = Field(default_factory=dict)

    model_config = {"extra": "ignore"}


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
    pets: list[PetCreate] = Field(..., min_length=3, max_length=3)


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
    season_status: SeasonStatus | None = None
    # When the team's pets are released (the game locks them until then)
    season_ends_at: datetime | None = None
    final_rank: int | None = None
    pets: list[PetResponse]
    created_at: datetime
    updated_at: datetime
    # Populated by /teams/current and team creation (arena hub view)
    rank: int | None = None
    daily_battles_remaining: int | None = None

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
    rewarded_coins: int = 0
    is_active: bool = True
    season_id: UUID | None = None
    season_name: str | None = None
    season_status: SeasonStatus | None = None
    season_ends_at: datetime | None = None
    final_rank: int | None = None
    # Per-user rank within the team's season (1-indexed).  Populated when
    # the list endpoint can derive it; None for legacy callers.
    rank: int | None = None
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
    # "attack" (this team attacked) or "defense" (it was attacked)
    role: str = "attack"
    won: bool
    is_draw: bool = False
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


class ArenaModuleResponse(BaseModel):
    """A module the arena can field this season."""

    name: str
    version: str
    monsters: int


class ArenaModulesResponse(BaseModel):
    """Modules on the running season's Omnipet runtime."""

    runtime_version: str | None = None
    modules: list[ArenaModuleResponse]
