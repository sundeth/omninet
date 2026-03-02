"""
Module service for managing game modules.
"""
import json
import zipfile
from io import BytesIO
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from omninet.config import settings
from omninet.models.logs import ActivityType
from omninet.models.module import GameModule, ModuleCategory, ModuleContributor, ModuleStatus
from omninet.models.user import User
from omninet.services.logging import LoggingService
from omninet.services.user import UserService


class ModuleService:
    """Service for module-related operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.logging_service = LoggingService(db)
        self.user_service = UserService(db)

    async def get_by_id(self, module_id: UUID) -> GameModule | None:
        """Get module by ID."""
        query = (
            select(GameModule)
            .options(
                selectinload(GameModule.owner),
                selectinload(GameModule.category),
                selectinload(GameModule.contributors).selectinload(ModuleContributor.user),
            )
            .where(GameModule.id == module_id)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> GameModule | None:
        """Get module by name."""
        query = (
            select(GameModule)
            .options(
                selectinload(GameModule.owner),
                selectinload(GameModule.category),
            )
            .where(func.lower(GameModule.name) == name.lower())
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_create_category(
        self, name: str, description: str = ""
    ) -> ModuleCategory:
        """Get or create a module category."""
        query = select(ModuleCategory).where(
            func.lower(ModuleCategory.name) == name.lower()
        )
        result = await self.db.execute(query)
        category = result.scalar_one_or_none()

        if not category:
            category = ModuleCategory(name=name, description=description)
            self.db.add(category)
            await self.db.flush()

        return category

    async def get_categories(self) -> list[ModuleCategory]:
        """Get all categories."""
        query = select(ModuleCategory).order_by(ModuleCategory.display_order)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def check_publish_permission(
        self, user: User, module_name: str, version: str
    ) -> dict:
        """
        Check if user can publish a module.
        Returns dict with can_publish, is_new, is_update, message, module_id.
        """
        module = await self.get_by_name(module_name)

        if module is None:
            # New module
            return {
                "can_publish": True,
                "is_new": True,
                "is_update": False,
                "message": "Ready to publish new module",
                "module_id": None,
            }

        # Check if user is owner
        if module.owner_id == user.id:
            return {
                "can_publish": True,
                "is_new": False,
                "is_update": True,
                "message": "Ready to update existing module",
                "module_id": module.id,
            }

        # Check if user is contributor
        is_contributor = any(c.user_id == user.id for c in module.contributors)
        if is_contributor:
            return {
                "can_publish": True,
                "is_new": False,
                "is_update": True,
                "message": "Ready to update module as contributor",
                "module_id": module.id,
            }

        return {
            "can_publish": False,
            "is_new": False,
            "is_update": False,
            "message": "Module name is reserved by another user",
            "module_id": module.id,
        }

    async def create_module(
        self,
        owner_id: UUID,
        name: str,
        version: str,
        description: str | None = None,
        category_name: str | None = None,
    ) -> GameModule:
        """Create a new module."""
        category = None
        if category_name:
            category = await self.get_or_create_category(category_name)

        module = GameModule(
            owner_id=owner_id,
            name=name,
            version=version,
            description=description,
            category_id=category.id if category else None,
            status=ModuleStatus.DRAFT,
        )
        self.db.add(module)
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.MODULE_CREATED,
            user_id=owner_id,
            target_id=module.id,
            target_type="module",
            description=f"Module {name} created",
        )

        return module

    async def update_module(
        self,
        module: GameModule,
        version: str | None = None,
        description: str | None = None,
        category_name: str | None = None,
    ) -> GameModule:
        """Update module metadata."""
        if version:
            module.version = version
        if description is not None:
            module.description = description
        if category_name:
            category = await self.get_or_create_category(category_name)
            module.category_id = category.id

        await self.db.flush()
        await self.db.refresh(module)

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.MODULE_UPDATED,
            user_id=module.owner_id,
            target_id=module.id,
            target_type="module",
            description=f"Module {module.name} updated to v{module.version}",
        )

        return module

    async def publish_module(
        self,
        user: User,
        module_name: str,
        zip_data: bytes,
    ) -> tuple[bool, str, GameModule | None]:
        """
        Publish or update a module from zip file.
        Returns (success, message, module).
        """
        try:
            # Read zip file
            zip_buffer = BytesIO(zip_data)
            with zipfile.ZipFile(zip_buffer, "r") as zf:
                # Find and read module.json
                module_json = None
                for name in zf.namelist():
                    if name.endswith("module.json"):
                        with zf.open(name) as f:
                            module_json = json.load(f)
                        break

                if not module_json:
                    return False, "module.json not found in zip file", None

                # Extract module info
                name = module_json.get("name", module_name)
                version = module_json.get("version", "1.0.0")
                description = module_json.get("description", "")
                category_name = module_json.get("category", "Custom")

            # Check permission
            permission = await self.check_publish_permission(user, name, version)
            if not permission["can_publish"]:
                return False, permission["message"], None

            # Create or get module
            if permission["is_new"]:
                module = await self.create_module(
                    owner_id=user.id,
                    name=name,
                    version=version,
                    description=description,
                    category_name=category_name,
                )
            else:
                module = await self.get_by_id(permission["module_id"])
                if not module:
                    return False, "Module not found", None
                module = await self.update_module(
                    module=module,
                    version=version,
                    description=description,
                    category_name=category_name,
                )

            # Save zip file
            file_name = f"{module.id}_{version}.zip"
            file_path = settings.modules_path / file_name

            with open(file_path, "wb") as f:
                f.write(zip_data)

            # Update module file info
            module.file_name = file_name
            module.file_size = len(zip_data)
            module.status = ModuleStatus.PUBLISHED

            await self.db.flush()

            # Log activity
            await self.logging_service.log_activity(
                activity_type=ActivityType.MODULE_PUBLISHED,
                user_id=user.id,
                target_id=module.id,
                target_type="module",
                description=f"Module {name} v{version} published",
                log_metadata={"version": version, "size": len(zip_data)},
            )

            return True, "Module published successfully", module

        except json.JSONDecodeError:
            return False, "Invalid module.json format", None
        except zipfile.BadZipFile:
            return False, "Invalid zip file", None
        except Exception as e:
            return False, f"Error publishing module: {str(e)}", None

    async def unpublish_module(
        self,
        user: User,
        module_id: UUID,
    ) -> tuple[bool, str]:
        """Unpublish a module (only owner can do this)."""
        module = await self.get_by_id(module_id)
        if not module:
            return False, "Module not found"

        if module.owner_id != user.id:
            return False, "Only the owner can unpublish a module"

        module.status = ModuleStatus.UNPUBLISHED
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.MODULE_UNPUBLISHED,
            user_id=user.id,
            target_id=module.id,
            target_type="module",
            description=f"Module {module.name} unpublished",
        )

        return True, "Module unpublished successfully"

    async def get_module_file(self, module_id: UUID) -> tuple[bytes, str] | None:
        """Get module zip file data and filename."""
        module = await self.get_by_id(module_id)
        if not module or not module.file_name:
            return None

        file_path = settings.modules_path / module.file_name
        if not file_path.exists():
            return None

        with open(file_path, "rb") as f:
            data = f.read()

        # Increment download count
        module.download_count += 1
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.MODULE_DOWNLOADED,
            target_id=module.id,
            target_type="module",
            description=f"Module {module.name} downloaded",
        )

        return data, module.file_name

    async def list_modules(
        self,
        category_id: UUID | None = None,
        status: ModuleStatus | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GameModule], int]:
        """List modules with optional filters."""
        query = (
            select(GameModule)
            .options(
                selectinload(GameModule.owner),
                selectinload(GameModule.category),
            )
        )

        # Apply filters
        if category_id:
            query = query.where(GameModule.category_id == category_id)
        if status:
            query = query.where(GameModule.status == status)
        else:
            # Default to published modules
            query = query.where(GameModule.status == ModuleStatus.PUBLISHED)
        if search:
            search_pattern = f"%{search}%"
            query = query.where(
                or_(
                    GameModule.name.ilike(search_pattern),
                    GameModule.description.ilike(search_pattern),
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar_one()

        # Apply pagination
        query = (
            query.order_by(GameModule.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(query)
        modules = list(result.scalars().all())

        return modules, total

    async def get_user_modules(self, user_id: UUID) -> list[GameModule]:
        """Get all modules owned by or contributed to by a user."""
        query = (
            select(GameModule)
            .options(
                selectinload(GameModule.owner),
                selectinload(GameModule.category),
                selectinload(GameModule.contributors),
            )
            .outerjoin(ModuleContributor)
            .where(
                or_(
                    GameModule.owner_id == user_id,
                    ModuleContributor.user_id == user_id,
                )
            )
            .distinct()
            .order_by(GameModule.updated_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_contributor(
        self,
        owner: User,
        module_id: UUID,
        contributor_nickname: str,
    ) -> tuple[bool, str]:
        """Add a contributor to a module."""
        module = await self.get_by_id(module_id)
        if not module:
            return False, "Module not found"

        if module.owner_id != owner.id:
            return False, "Only the owner can manage contributors"

        # Find contributor user
        contributor = await self.user_service.get_by_nickname(contributor_nickname)
        if not contributor:
            return False, f"User '{contributor_nickname}' not found"

        if contributor.id == owner.id:
            return False, "Cannot add yourself as a contributor"

        # Check if already a contributor
        existing = any(c.user_id == contributor.id for c in module.contributors)
        if existing:
            return False, f"'{contributor_nickname}' is already a contributor"

        # Add contributor
        mc = ModuleContributor(
            user_id=contributor.id,
            module_id=module.id,
            added_by=owner.id,
        )
        self.db.add(mc)
        await self.db.flush()

        # Log activity
        await self.logging_service.log_activity(
            activity_type=ActivityType.MODULE_CONTRIBUTOR_ADDED,
            user_id=owner.id,
            target_id=module.id,
            target_type="module",
            description=f"Contributor {contributor_nickname} added to {module.name}",
            log_metadata={"contributor_id": str(contributor.id)},
        )

        return True, f"'{contributor_nickname}' added as contributor"

    async def remove_contributor(
        self,
        owner: User,
        module_id: UUID,
        contributor_nickname: str,
    ) -> tuple[bool, str]:
        """Remove a contributor from a module."""
        module = await self.get_by_id(module_id)
        if not module:
            return False, "Module not found"

        if module.owner_id != owner.id:
            return False, "Only the owner can manage contributors"

        # Find contributor
        contributor = await self.user_service.get_by_nickname(contributor_nickname)
        if not contributor:
            return False, f"User '{contributor_nickname}' not found"

        # Find and remove contributor relationship
        for mc in module.contributors:
            if mc.user_id == contributor.id:
                await self.db.delete(mc)
                await self.db.flush()

                # Log activity
                await self.logging_service.log_activity(
                    activity_type=ActivityType.MODULE_CONTRIBUTOR_REMOVED,
                    user_id=owner.id,
                    target_id=module.id,
                    target_type="module",
                    description=f"Contributor {contributor_nickname} removed from {module.name}",
                )

                return True, f"'{contributor_nickname}' removed from contributors"

        return False, f"'{contributor_nickname}' is not a contributor"

    async def get_contributors(self, module_id: UUID) -> list[ModuleContributor]:
        """Get all contributors for a module."""
        query = (
            select(ModuleContributor)
            .options(selectinload(ModuleContributor.user))
            .where(ModuleContributor.module_id == module_id)
            .order_by(ModuleContributor.added_at)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_contributors(
        self,
        owner: User,
        module_id: UUID,
        contributor_nicknames: list[str],
    ) -> tuple[bool, str, list[str]]:
        """
        Update the list of contributors for a module.
        Returns (success, message, invalid_nicknames).
        """
        module = await self.get_by_id(module_id)
        if not module:
            return False, "Module not found", []

        if module.owner_id != owner.id:
            return False, "Only the owner can manage contributors", []

        # Validate all nicknames
        valid_users = await self.user_service.get_users_by_nicknames(contributor_nicknames)
        valid_nicknames = {u.nickname.lower() for u in valid_users}
        invalid_nicknames = [
            n for n in contributor_nicknames if n.lower() not in valid_nicknames
        ]

        if invalid_nicknames:
            return False, f"Some users not found: {', '.join(invalid_nicknames)}", invalid_nicknames

        # Get current contributors
        current_ids = {c.user_id for c in module.contributors}
        new_ids = {u.id for u in valid_users if u.id != owner.id}

        # Remove contributors not in new list
        for mc in module.contributors:
            if mc.user_id not in new_ids:
                await self.db.delete(mc)

        # Add new contributors
        for user in valid_users:
            if user.id != owner.id and user.id not in current_ids:
                mc = ModuleContributor(
                    user_id=user.id,
                    module_id=module.id,
                    added_by=owner.id,
                )
                self.db.add(mc)

        await self.db.flush()

        return True, "Contributors updated successfully", []
