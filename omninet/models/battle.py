"""
Battle and team related database models.
"""
import enum
import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omninet.database import Base

if TYPE_CHECKING:
    from omninet.models.user import User


class SeasonStatus(enum.Enum):
    """Status of a season."""

    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"


class BattleResult(enum.Enum):
    """Result of a battle."""

    TEAM1_WIN = "team1_win"
    TEAM2_WIN = "team2_win"
    DRAW = "draw"


class Season(Base):
    """
    An arena season.

    A season runs from ``starts_at`` to ``ends_at`` (``start_date`` /
    ``end_date`` are their dates, kept for older clients).  Its
    ``restrictions`` limit which Digimon may join (checked by the arena
    engine on the server's module data); its ``config`` overrides the
    server's battle settings (see omninet/arena/rules.py).  Battles run on
    the Omnipet runtime snapshot named by ``runtime_version``.
    """

    __tablename__ = "seasons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SeasonStatus] = mapped_column(
        Enum(SeasonStatus, values_callable=lambda obj: [e.value for e in obj], create_type=False),
        default=SeasonStatus.UPCOMING,
    )

    # Season restrictions (JSON for flexibility)
    # Example: {"allowed_stages": [3, 4, 5], "allowed_attributes": ["Vaccine", "Data"], "allowed_modules": ["DMX", "DM20"]}
    # Attributes may be written as names or as the Va/Da/Vi codes; "Free"
    # matches Digimon with no attribute.
    restrictions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Battle settings for this season, e.g. {"attacks_per_day": 20, "charge": "random"}
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Omnipet runtime snapshot the season fights on
    runtime_version: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Top-3 prizes credited (set once, at close)
    prizes_paid: Mapped[bool] = mapped_column(Boolean, default=False)

    # Reward multiplier for this season
    reward_multiplier: Mapped[float] = mapped_column(default=1.0)

    # Season theme metadata
    theme_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    banner_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    teams: Mapped[list["GameTeam"]] = relationship("GameTeam", back_populates="season")

    def __repr__(self) -> str:
        return f"<Season(name={self.name}, starts={self.starts_at}, ends={self.ends_at})>"


class GameTeam(Base):
    """Team of pets for online battles."""

    __tablename__ = "game_teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    rewarded_coins: Mapped[int] = mapped_column(Integer, default=0)
    reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Rank when the season closed (None while it runs)
    final_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Development dummy player's team
    is_dummy: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="teams")
    season: Mapped[Optional["Season"]] = relationship("Season", back_populates="teams")
    pets: Mapped[list["GamePet"]] = relationship(
        "GamePet", back_populates="team", cascade="all, delete-orphan"
    )
    battles_as_team1: Mapped[list["GameBattle"]] = relationship(
        "GameBattle",
        back_populates="team1",
        foreign_keys="GameBattle.team1_id",
    )
    battles_as_team2: Mapped[list["GameBattle"]] = relationship(
        "GameBattle",
        back_populates="team2",
        foreign_keys="GameBattle.team2_id",
    )

    def __repr__(self) -> str:
        return f"<GameTeam(id={self.id}, owner_id={self.owner_id}, score={self.score})>"

    @property
    def total_battles(self) -> int:
        """Get total battles fought."""
        return self.wins + self.losses + self.draws


class GamePet(Base):
    """A Digimon on an arena team.

    The stat columns hold what the arena engine computed from the server's
    module data and the uploaded care status -- never values the client
    sent.  ``extra_data`` keeps ``slot`` (team order), ``arena_entry`` (the
    engine's battle entry) and ``upload`` (what the client sent).
    """

    __tablename__ = "game_pets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_teams.id", ondelete="SET NULL"), nullable=True
    )

    # Pet identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    module_name: Mapped[str] = mapped_column(String(200), nullable=False)
    module_version: Mapped[str] = mapped_column(String(50), nullable=False)
    pet_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Pet stats
    stage: Mapped[int] = mapped_column(Integer, default=1)
    level: Mapped[int] = mapped_column(Integer, default=1)
    atk_main: Mapped[str] = mapped_column(String(100), nullable=True)
    atk_alt: Mapped[str | None] = mapped_column(String(100), nullable=True)
    atk_alt2: Mapped[str | None] = mapped_column(String(100), nullable=True)
    power: Mapped[int] = mapped_column(Integer, default=0)
    attribute: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hp: Mapped[int] = mapped_column(Integer, default=100)
    star: Mapped[int] = mapped_column(Integer, default=1)
    critical_turn: Mapped[int] = mapped_column(Integer, default=0)

    # Additional pet data (JSON for flexibility)
    extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    team: Mapped[Optional["GameTeam"]] = relationship("GameTeam", back_populates="pets")

    def __repr__(self) -> str:
        return f"<GamePet(name={self.name}, module={self.module_name})>"


class GameBattle(Base):
    """Record of a battle between two teams."""

    __tablename__ = "game_battles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    team1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False
    )
    team2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_teams.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=True
    )
    winner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_teams.id"), nullable=True
    )
    result: Mapped[BattleResult] = mapped_column(
        Enum(BattleResult, values_callable=lambda obj: [e.value for e in obj], create_type=False),
        nullable=False,
    )

    # Battle log (JSON containing the full battle replay data).  team1 is
    # always the attacker.  Version 2 logs carry the engine's result, both
    # teams' battle entries, the starting HP, seed and rules (see
    # BattleService._execute_battle); the game replays them.
    battle_log: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Battle metadata
    team1_score_change: Mapped[int] = mapped_column(Integer, default=0)
    team2_score_change: Mapped[int] = mapped_column(Integer, default=0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)

    fought_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Unique constraint to prevent rematches on same day
    __table_args__ = (
        UniqueConstraint(
            "team1_id", "team2_id", "fought_at",
            name="uq_battle_teams_date"
        ),
    )

    # Relationships
    team1: Mapped["GameTeam"] = relationship(
        "GameTeam", back_populates="battles_as_team1", foreign_keys=[team1_id]
    )
    team2: Mapped["GameTeam"] = relationship(
        "GameTeam", back_populates="battles_as_team2", foreign_keys=[team2_id]
    )

    def __repr__(self) -> str:
        return f"<GameBattle(team1={self.team1_id}, team2={self.team2_id}, result={self.result})>"
