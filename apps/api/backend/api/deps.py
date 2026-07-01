from typing import Annotated

from fastapi import Depends

from backend.api.auth import CurrentUser, current_user, optional_current_user

UserDep = Annotated[CurrentUser, Depends(current_user)]
OptionalUserDep = Annotated[CurrentUser | None, Depends(optional_current_user)]
