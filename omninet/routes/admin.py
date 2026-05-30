"""
Admin routes.
"""
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from omninet.config import settings
from omninet.models.logs import ActivityType
from omninet.models.module import ModuleStatus
from omninet.routes.deps import AdminUser, DbSession
from omninet.schemas.common import MessageResponse
from omninet.services.logging import LoggingService
from omninet.services.module import ModuleService
from omninet.services.season import SeasonService
from omninet.services.team import TeamService
from omninet.services.user import UserService

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Dev-only seeding endpoint
# ---------------------------------------------------------------------------

# DMC pets used to seed every dummy team — values copied from
# Omnipet/modules/DMC/monster.json so the server-side rank battle code sees
# legitimate stage-4 pets with non-zero power.  atk_main is stringified to
# match the GamePet.atk_main column type.
_DUMMY_TEAM_PETS = [
    {
        "name": "Greymon",
        "module_name": "DMC",
        "module_version": "1.0",
        "pet_version": "1",
        "stage": 4,
        "level": 1,
        "atk_main": "4",
        "atk_alt": None,
        "atk_alt2": None,
        "power": 50,
        "attribute": "Va",
        "hp": 100,
        "star": 1,
        "critical_turn": 0,
        "extra_data": {"seeded": True, "source": "dev_dummy_teams"},
    },
    {
        "name": "Garurumon",
        "module_name": "DMC",
        "module_version": "1.0",
        "pet_version": "2",
        "stage": 4,
        "level": 1,
        "atk_main": "4",
        "atk_alt": None,
        "atk_alt2": None,
        "power": 45,
        "attribute": "Va",
        "hp": 100,
        "star": 1,
        "critical_turn": 0,
        "extra_data": {"seeded": True, "source": "dev_dummy_teams"},
    },
    {
        "name": "Ogremon",
        "module_name": "DMC",
        "module_version": "1.0",
        "pet_version": "3",
        "stage": 4,
        "level": 1,
        "atk_main": "7",
        "atk_alt": None,
        "atk_alt2": None,
        "power": 50,
        "attribute": "Vi",
        "hp": 100,
        "star": 1,
        "critical_turn": 0,
        "extra_data": {"seeded": True, "source": "dev_dummy_teams"},
    },
]


class SeedDummyTeamsResponse(BaseModel):
    accounts_created: int
    accounts_reused: int
    teams_created: int
    teams_skipped_existing: int
    season_name: str
    accounts: list[str]


@router.post("/dev/seed-dummy-teams", response_model=SeedDummyTeamsResponse)
async def seed_dummy_teams(db: DbSession):
    """Create ``account1``..``account10`` plus a 3-pet team for the current
    season for each one — DEV ENVIRONMENT ONLY.

    Used to stand up enough server-side rank-battle opponents that the
    matchmaking code has someone to pair against.  All ten teams share the
    same Greymon / Garurumon / Ogremon trio from the DMC module.

    Refuses to run unless ``settings.environment == "dev"``.  Safe to
    re-run: accounts and teams that already exist are skipped rather than
    duplicated.
    """
    if not settings.is_dev:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is dev-only",
        )

    user_service = UserService(db)
    season_service = SeasonService(db)
    team_service = TeamService(db)

    season = await season_service.get_or_create_weekly_season()

    accounts_created = 0
    accounts_reused = 0
    teams_created = 0
    teams_skipped_existing = 0
    account_names: list[str] = []

    for i in range(1, 11):
        nickname = f"account{i}"
        email = f"account{i}@dev.local"
        account_names.append(nickname)

        # Reuse existing user with same nickname (safe re-run) or create new.
        user = await user_service.get_by_nickname(nickname)
        if user is None:
            user = await user_service.create_user(
                nickname=nickname,
                email=email,
                password="devdummy",
                type_name="Standard",
                is_verified=True,
                is_active=True,
            )
            accounts_created += 1
        else:
            accounts_reused += 1

        # Don't create a duplicate team for the active season.
        existing = await team_service.get_user_current_team(user.id)
        if existing is not None and existing.season_id == season.id:
            teams_skipped_existing += 1
            continue

        ok, msg, _team = await team_service.create_team(
            user=user,
            pets_data=_DUMMY_TEAM_PETS,
            team_name=f"{nickname}'s squad",
        )
        if ok:
            teams_created += 1
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Team creation failed for {nickname}: {msg}",
            )

    await db.commit()

    return SeedDummyTeamsResponse(
        accounts_created=accounts_created,
        accounts_reused=accounts_reused,
        teams_created=teams_created,
        teams_skipped_existing=teams_skipped_existing,
        season_name=season.name,
        accounts=account_names,
    )


@router.post("/users/{user_id}/ban", response_model=MessageResponse)
async def ban_user(
    user_id: UUID,
    admin_user: AdminUser,
    db: DbSession,
):
    """Ban a user (admin only)."""
    user_service = UserService(db)
    logging_service = LoggingService(db)

    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await user_service.update_user(user, is_active=False)

    await logging_service.log_activity(
        activity_type=ActivityType.ADMIN_USER_BANNED,
        user_id=admin_user.id,
        target_id=user.id,
        target_type="user",
        description=f"User {user.nickname} banned by {admin_user.nickname}",
    )

    return MessageResponse(message=f"User {user.nickname} has been banned")


@router.post("/users/{user_id}/unban", response_model=MessageResponse)
async def unban_user(
    user_id: UUID,
    admin_user: AdminUser,
    db: DbSession,
):
    """Unban a user (admin only)."""
    user_service = UserService(db)

    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user = await user_service.update_user(user, is_active=True)

    return MessageResponse(message=f"User {user.nickname} has been unbanned")


@router.post("/users/{user_id}/coins", response_model=MessageResponse)
async def adjust_user_coins(
    user_id: UUID,
    amount: int,
    admin_user: AdminUser,
    db: DbSession,
):
    """Adjust a user's coin balance (admin only)."""
    user_service = UserService(db)
    logging_service = LoggingService(db)

    user = await user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    old_balance = user.coins
    user = await user_service.update_coins(user, amount)

    await logging_service.log_activity(
        activity_type=ActivityType.ADMIN_CONFIG_CHANGED,
        user_id=admin_user.id,
        target_id=user.id,
        target_type="user",
        description=f"Coins adjusted for {user.nickname}: {old_balance} -> {user.coins}",
        log_metadata={"old_balance": old_balance, "new_balance": user.coins, "change": amount},
    )

    return MessageResponse(
        message=f"Coins adjusted: {old_balance} -> {user.coins} (change: {amount:+d})"
    )


@router.post("/modules/{module_id}/ban", response_model=MessageResponse)
async def ban_module(
    module_id: UUID,
    admin_user: AdminUser,
    db: DbSession,
):
    """Ban a module (admin only)."""
    module_service = ModuleService(db)
    logging_service = LoggingService(db)

    module = await module_service.get_by_id(module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    module.status = ModuleStatus.BANNED
    await db.flush()

    await logging_service.log_activity(
        activity_type=ActivityType.MODULE_BANNED,
        user_id=admin_user.id,
        target_id=module.id,
        target_type="module",
        description=f"Module {module.name} banned by {admin_user.nickname}",
    )

    return MessageResponse(message=f"Module {module.name} has been banned")


@router.post("/modules/{module_id}/unban", response_model=MessageResponse)
async def unban_module(
    module_id: UUID,
    admin_user: AdminUser,
    db: DbSession,
):
    """Unban a module (admin only)."""
    module_service = ModuleService(db)

    module = await module_service.get_by_id(module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found",
        )

    module.status = ModuleStatus.PUBLISHED
    await db.flush()

    return MessageResponse(message=f"Module {module.name} has been unbanned")


@router.post("/seasons/update-statuses", response_model=MessageResponse)
async def update_season_statuses(
    admin_user: AdminUser,
    db: DbSession,
):
    """Update all season statuses based on dates (admin only)."""
    season_service = SeasonService(db)
    await season_service.update_season_statuses()

    return MessageResponse(message="Season statuses updated")


@router.get("/logs")
async def get_activity_logs(
    admin_user: AdminUser,
    db: DbSession,
    activity_type: str | None = None,
    user_id: UUID | None = None,
    target_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """Get activity logs (admin only)."""
    logging_service = LoggingService(db)

    if user_id:
        logs = await logging_service.get_user_activity(user_id, limit=limit)
    elif target_id:
        logs = await logging_service.get_target_activity(target_id, limit=limit)
    else:
        activity_types = None
        if activity_type:
            try:
                activity_types = [ActivityType(activity_type)]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid activity type: {activity_type}",
                )
        logs = await logging_service.get_recent_activity(
            limit=limit, activity_types=activity_types
        )

    return [
        {
            "id": str(log.id),
            "activity_type": log.activity_type.value,
            "user_id": str(log.user_id) if log.user_id else None,
            "target_id": str(log.target_id) if log.target_id else None,
            "target_type": log.target_type,
            "description": log.description,
            "metadata": log.metadata,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
