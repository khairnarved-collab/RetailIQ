"""
Authentication endpoints: register, login, profile, password change/reset.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import RateLimiter
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_reset_token,
    verify_password,
)
from app.database.session import get_db
from app.models import Notification, Role, User
from app.schemas.auth import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    ProfileUpdateIn,
    RegisterIn,
    ResetPasswordIn,
    TokenOut,
    UserOut,
)

UTC = timezone.utc  # datetime.UTC needs Python 3.11+; this works on 3.10 too

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
auth_limiter = RateLimiter(settings.RATE_LIMIT_AUTH_PER_MIN, scope="auth")


def _token_response(user: User) -> TokenOut:
    token = create_access_token(user.id, user.role.value)
    return TokenOut(access_token=token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=201, dependencies=[Depends(auth_limiter)])
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if not settings.ALLOW_PUBLIC_SIGNUP:
        raise HTTPException(403, "Public sign-up is disabled. Ask an administrator for an account.")
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    # Self-registered users are always analysts; only admins can create admins.
    user = User(email=email, full_name=body.full_name.strip(), hashed_password=hash_password(body.password),
                role=Role.ANALYST)
    db.add(user)
    db.flush()
    db.add(Notification(user_id=user.id, level="info", title="Welcome to RetailIQ",
                        message="Explore the dashboard, run a demand forecast, or upload your own data in Data Management.",
                        link="/app/dashboard"))
    db.commit()
    db.refresh(user)
    log.info("New user registered: %s", email)
    return _token_response(user)


@router.post("/login", response_model=TokenOut, dependencies=[Depends(auth_limiter)])
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    # Same error for "no such user" and "wrong password" to avoid account enumeration.
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account has been deactivated")
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return _token_response(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.patch("/me", response_model=UserOut)
def update_profile(body: ProfileUpdateIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.job_title is not None:
        user.job_title = body.job_title.strip() or None
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if settings.is_protected_demo(user.email):
        raise HTTPException(403, "The password of a public demo account cannot be changed")
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    if body.current_password == body.new_password:
        raise HTTPException(400, "New password must be different from the current one")
    user.hashed_password = hash_password(body.new_password)
    db.commit()
    return {"message": "Password updated"}


@router.post("/forgot-password", dependencies=[Depends(auth_limiter)])
def forgot_password(body: ForgotPasswordIn, db: Session = Depends(get_db)):
    """
    Creates a one-time reset token valid for PASSWORD_RESET_EXPIRE_MINUTES.

    No email server is configured in this project, so in development mode
    (EXPOSE_RESET_TOKEN=true) the token is returned in the response and logged.
    In production you would email the link instead and set EXPOSE_RESET_TOKEN=false.
    """
    generic = {"message": "If an account exists for this email, a password reset link has been created."}
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active or settings.is_protected_demo(user.email):
        return generic
    token, token_hash = new_reset_token()
    user.reset_token_hash = token_hash
    user.reset_token_expires = datetime.now(UTC) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES)
    db.commit()
    log.info("Password reset requested for %s (token valid %s min)", user.email, settings.PASSWORD_RESET_EXPIRE_MINUTES)
    if settings.EXPOSE_RESET_TOKEN:
        return {**generic, "dev_reset_token": token,
                "dev_note": "Development mode: no email server is configured, so the token is shown here."}
    return generic


@router.post("/reset-password", dependencies=[Depends(auth_limiter)])
def reset_password(body: ResetPasswordIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.reset_token_hash == hash_token(body.token)))
    expires = user.reset_token_expires if user else None
    if expires is not None and expires.tzinfo is None:  # SQLite returns naive datetimes
        expires = expires.replace(tzinfo=UTC)
    if user is None or expires is None or expires < datetime.now(UTC):
        raise HTTPException(400, "This reset link is invalid or has expired")
    user.hashed_password = hash_password(body.new_password)
    user.reset_token_hash = None
    user.reset_token_expires = None
    db.commit()
    return {"message": "Password has been reset. You can now log in."}
