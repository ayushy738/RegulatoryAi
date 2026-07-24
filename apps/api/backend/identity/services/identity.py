from uuid import UUID

from backend.identity.models import IdentityProfileModel, IdentityUserModel
from backend.identity.repositories.profiles import ProfilesRepository
from backend.identity.repositories.users import UsersRepository


class IdentityService:
    """Persistence facade for identity users and profiles.

    This service intentionally contains no registration, login, or migration
    behavior. Transaction boundaries remain with the caller.
    """

    def __init__(
        self,
        users: UsersRepository,
        profiles: ProfilesRepository,
    ) -> None:
        self._users = users
        self._profiles = profiles

    def add_user(self, user: IdentityUserModel) -> IdentityUserModel:
        return self._users.add(user)

    def get_user(self, user_id: UUID) -> IdentityUserModel | None:
        return self._users.get(user_id)

    def get_user_by_normalized_email(
        self,
        email_normalized: str,
    ) -> IdentityUserModel | None:
        return self._users.get_by_normalized_email(email_normalized)

    def save_user(self, user: IdentityUserModel) -> IdentityUserModel:
        return self._users.save(user)

    def delete_user(self, user: IdentityUserModel) -> None:
        self._users.delete(user)

    def add_profile(self, profile: IdentityProfileModel) -> IdentityProfileModel:
        return self._profiles.add(profile)

    def get_profile(self, user_id: UUID) -> IdentityProfileModel | None:
        return self._profiles.get(user_id)

    def save_profile(self, profile: IdentityProfileModel) -> IdentityProfileModel:
        return self._profiles.save(profile)

    def delete_profile(self, profile: IdentityProfileModel) -> None:
        self._profiles.delete(profile)
