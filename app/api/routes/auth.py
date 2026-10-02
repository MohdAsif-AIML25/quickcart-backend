from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import login_rate_limiter
from app.models import User
from app.schemas.auth import RefreshRequest, TokenPair, UserCreate, UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=201,
    summary="Register a new user",
    responses={409: {"description": "Email already registered"}},
)
def register(data: UserCreate, db: DbSession) -> User:
    return auth_service.register_user(db, data)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Log in and receive access + refresh tokens",
    description="OAuth2 form: put your **email** in the `username` field.",
    responses={
        401: {"description": "Invalid credentials"},
        429: {"description": "Too many attempts"},
    },
    dependencies=[Depends(login_rate_limiter)],
)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> TokenPair:
    user = auth_service.authenticate_user(db, form.username, form.password)
    return auth_service.issue_tokens(user)


@router.post("/refresh", response_model=TokenPair, summary="Exchange a refresh token for new tokens")
def refresh(data: RefreshRequest, db: DbSession) -> TokenPair:
    return auth_service.refresh_tokens(db, data.refresh_token)


@router.get("/me", response_model=UserRead, summary="Get the current user")
def me(user: CurrentUser) -> User:
    return user
