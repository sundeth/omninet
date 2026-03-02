"""
Battle and team related database models.
"""
import enum
import uuid
from datetime import datetime, date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
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
    JSON,
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
    Season configuration for themed battles.
    Seasons can restrict which pets can participate based on stage, attribute, or module.
    """

    __tablename__ = "seasons"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[SeasonStatus] = mapped_column(
        Enum(SeasonStatus), default=SeasonStatus.UPCOMING
    )

    # Season restrictions (JSON for flexibility)
    # Example: {"allowed_stages": [3, 4, 5], "allowed_attributes": ["Vaccine", "Data"], "allowed_modules": ["DMX", "DM20"]}
    restrictions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Reward multiplier for this season
    reward_multiplier: Mapped[float] = mapped_column(default=1.0)

    # Season theme metadata
    theme_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    banner_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    teams: Mapped[list["GameTeam"]] = relationship("GameTeam", back_populates="season")

    def __repr__(self) -> str:
        return f"<Season(name={self.name}, start={self.start_date}, end={self.end_date})>"

    def is_pet_allowed(self, pet: "GamePet") -> bool:
        """Check if a pet is allowed in this season based on restrictions."""
        if not self.restrictions:
            return True

        # Check stage restriction
        if "allowed_stages" in self.restrictions:
            if pet.stage not in self.restrictions["allowed_stages"]:
                return False

        # Check attribute restriction
        if "allowed_attributes" in self.restrictions:
            if pet.attribute not in self.restrictions["allowed_attributes"]:
                return False

        # Check module restriction
        if "allowed_modules" in self.restrictions:
            if pet.module_name not in self.restrictions["allowed_modules"]:
                return False

        return True


class GameTeam(Base):
    """Team of pets for online battles."""

    __tablename__ = "game_teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    losses: Mapped[int] = mapped_column(Integer, default=0)
    draws: Mapped[int] = mapped_column(Integer, default=0)
    rewarded_coins: Mapped[int] = mapped_column(Integer, default=0)
    reward_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
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
    """Pet uploaded by users for online battles."""

    __tablename__ = "game_pets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_teams.id", ondelete="SET NULL"), nullable=True
    )

    # Pet identity
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    module_name: Mapped[str] = mapped_column(String(200), nullable=False)
    module_version: Mapped[str] = mapped_column(String(50), nullable=False)
    pet_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Pet stats
    stage: Mapped[int] = mapped_column(Integer, default=1)
    level: Mapped[int] = mapped_column(Integer, default=1)
    atk_main: Mapped[str] = mapped_column(String(100), nullable=True)
    atk_alt: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    atk_alt2: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    power: Mapped[int] = mapped_column(Integer, default=0)
    attribute: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    hp: Mapped[int] = mapped_column(Integer, default=100)
    star: Mapped[int] = mapped_column(Integer, default=1)
    critical_turn: Mapped[int] = mapped_column(Integer, default=0)

    # Additional pet data (JSON for flexibility)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

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
    season_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=True
    )
    winner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("game_teams.id"), nullable=True
    )
    result: Mapped[BattleResult] = mapped_column(Enum(BattleResult), nullable=False)

    # Battle log (JSON containing the full battle replay data)
    battle_log: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

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
