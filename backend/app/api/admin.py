"""Admin-only endpoints: user management and application settings."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.database.session import get_db
from app.models import Role, User
from app.schemas.auth import AdminUserCreateIn, AdminUserUpdateIn, UserOut
from app.services import app_settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: AdminUserCreateIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    if db.scalar(select(User).where(func.lower(User.email) == body.email.lower())):
        raise HTTPException(409, "An account with this email already exists")
    user = User(email=body.email.lower(), full_name=body.full_name, role=body.role,
                hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: AdminUserUpdateIn, admin: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if settings.is_protected_demo(user.email) and (body.role is not None or body.is_active is not None):
        raise HTTPException(403, "The public demo accounts cannot be changed")
    if user.id == admin.id and (body.role == Role.ANALYST or body.is_active is False):
        raise HTTPException(400, "You cannot remove your own admin rights or deactivate yourself")
    for field in ("full_name", "role", "is_active"):
        val = getattr(body, field)
        if val is not None:
            setattr(user, field, val)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    if user.id == admin.id:
        raise HTTPException(400, "You cannot delete your own account")
    if settings.is_protected_demo(user.email):
        raise HTTPException(403, "The public demo accounts cannot be deleted")
    db.delete(user)
    db.commit()


# ---------------------------------------------------------------- settings
@router.get("/settings")
def read_settings(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Readable by everyone (the UI shows assumptions); only admins can change them."""
    return app_settings.get_all(db)


class SettingsUpdate(BaseModel):
    values: dict


@router.put("/settings/{section}")
def write_settings(section: str, body: SettingsUpdate, admin: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    try:
        return app_settings.update_section(db, section, body.values, admin.id)
    except KeyError:
        raise HTTPException(404, f"Unknown settings section '{section}'") from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
