from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.database.session import get_db
from app.models import User, UserRole

# auto_error=False: we raise our own UnauthorizedError, so every 401 has the same JSON shape
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)], db: DbSession
) -> User:
    """Authentication: who is calling? (valid access token -> active user)"""
    if token is None:
        raise UnauthorizedError("Not authenticated")
    user_id = decode_token(token, expected_type="access")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    """Authorization: is this user allowed to do it?"""
    if user.role != UserRole.ADMIN.value:
        raise ForbiddenError("Admin access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
