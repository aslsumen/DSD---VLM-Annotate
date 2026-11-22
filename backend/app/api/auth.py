"""Authentication, invitations and user administration (Sprint 3)."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import (
    Principal,
    get_db,
    require_authenticated,
    require_roles,
)
from ..errors import ApiError
from ..models import Invitation, User, UserRole, UserSession, utcnow
from ..schemas import (
    BootstrapRequest,
    InvitationAccept,
    InvitationCreate,
    InvitationCreated,
    LoginRequest,
    LoginResponse,
    UserOut,
)
from ..security import (
    DUMMY_PASSWORD_HASH,
    hash_password,
    hash_token,
    new_session_token,
    verify_password,
)

public_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalise_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or not _EMAIL_RE.fullmatch(email):
        raise ApiError(422, "INVALID_EMAIL", "a valid email address is required")
    return email


def _issue_session(session: Session, user: User, hours: int) -> tuple[str, datetime]:
    token = new_session_token()
    expires_at = utcnow() + timedelta(hours=hours)
    session.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=expires_at,
            last_seen_at=utcnow(),
        )
    )
    session.commit()
    return token, expires_at


def _login_response(user: User, token: str, expires_at: datetime) -> LoginResponse:
    return LoginResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserOut.model_validate(user),
    )


@public_router.post("/bootstrap", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def bootstrap_admin(
    payload: BootstrapRequest,
    request: Request,
    x_bootstrap_token: str | None = Header(default=None, alias="X-Bootstrap-Token"),
    session: Session = Depends(get_db),
) -> User:
    """Create the first administrator once, guarded by VLM_BOOTSTRAP_TOKEN.

    Disabled unless the environment sets a bootstrap secret.  Refuses as soon as
    any user exists, so it cannot be used to add a second backdoor account.
    """
    settings = request.app.state.settings
    if not settings.bootstrap_token:
        raise ApiError(
            403,
            "BOOTSTRAP_DISABLED",
            "bootstrap is disabled; set VLM_BOOTSTRAP_TOKEN to enable it",
        )
    if not x_bootstrap_token or not secrets.compare_digest(
        x_bootstrap_token, settings.bootstrap_token
    ):
        raise ApiError(403, "INVALID_BOOTSTRAP_TOKEN", "the bootstrap token is not valid")
    if session.scalar(select(func.count()).select_from(User)) > 0:
        raise ApiError(409, "ALREADY_BOOTSTRAPPED", "an administrator already exists")

    email = normalise_email(payload.email)
    if len(payload.password) < settings.password_min_length:
        raise ApiError(
            422,
            "PASSWORD_TOO_SHORT",
            f"password must be at least {settings.password_min_length} characters",
        )
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=UserRole.administrator,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@public_router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> LoginResponse:
    settings = request.app.state.settings
    email = normalise_email(payload.email)
    user = session.scalar(select(User).where(User.email == email))
    now = utcnow()

    if user is None:
        # Keep the failure path roughly constant-time.
        verify_password(payload.password, DUMMY_PASSWORD_HASH)
        raise ApiError(401, "INVALID_CREDENTIALS", "invalid email or password")

    if user.locked_until is not None and user.locked_until > now:
        raise ApiError(
            429,
            "ACCOUNT_LOCKED",
            "too many failed sign-in attempts; try again later",
        )

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.auth_max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.auth_lockout_minutes)
            user.failed_login_count = 0
        session.commit()
        raise ApiError(401, "INVALID_CREDENTIALS", "invalid email or password")

    if not user.is_active:
        raise ApiError(403, "ACCOUNT_DISABLED", "this account is disabled")

    user.failed_login_count = 0
    user.locked_until = None
    session.commit()
    token, expires_at = _issue_session(session, user, settings.auth_session_hours)
    session.refresh(user)
    return _login_response(user, token, expires_at)


@public_router.post(
    "/accept-invitation", response_model=LoginResponse, status_code=status.HTTP_201_CREATED
)
def accept_invitation(
    payload: InvitationAccept,
    request: Request,
    session: Session = Depends(get_db),
) -> LoginResponse:
    settings = request.app.state.settings
    invitation = session.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(payload.token))
    )
    now = utcnow()
    if invitation is None:
        raise ApiError(400, "INVITATION_INVALID", "the invitation token is not valid")
    if invitation.accepted_at is not None:
        raise ApiError(400, "INVITATION_ALREADY_USED", "this invitation was already used")
    if invitation.expires_at <= now:
        raise ApiError(400, "INVITATION_EXPIRED", "this invitation has expired")

    if len(payload.password) < settings.password_min_length:
        raise ApiError(
            422,
            "PASSWORD_TOO_SHORT",
            f"password must be at least {settings.password_min_length} characters",
        )
    existing = session.scalar(select(User).where(User.email == invitation.email))
    if existing is not None:
        raise ApiError(409, "EMAIL_ALREADY_EXISTS", "an account with this email already exists")

    user = User(
        email=invitation.email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=invitation.role,
    )
    session.add(user)
    session.flush()
    invitation.accepted_at = now
    token, expires_at = _issue_session(session, user, settings.auth_session_hours)
    session.refresh(user)
    return _login_response(user, token, expires_at)


@router.get("/me", response_model=UserOut)
def me(principal: Principal = Depends(require_authenticated)) -> User:
    assert principal.user is not None
    return principal.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    principal: Principal = Depends(require_authenticated),
    session: Session = Depends(get_db),
) -> Response:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and token:
        record = session.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        if record is not None and principal.user is not None and record.user_id == principal.user.id:
            record.revoked_at = utcnow()
            session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED
)
def create_invitation(
    payload: InvitationCreate,
    request: Request,
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
) -> InvitationCreated:
    """Dataset Administrators may invite Annotators only; admins may invite anyone."""
    settings = request.app.state.settings
    if principal.role == UserRole.dataset_admin and payload.role != UserRole.annotator:
        raise ApiError(
            403,
            "FORBIDDEN",
            "dataset administrators can only invite annotators",
        )
    email = normalise_email(payload.email)
    if session.scalar(select(User).where(User.email == email)) is not None:
        raise ApiError(409, "EMAIL_ALREADY_EXISTS", "an account with this email already exists")

    token = new_session_token()
    invitation = Invitation(
        email=email,
        role=payload.role,
        token_hash=hash_token(token),
        created_by_id=principal.user.id if principal.user is not None else None,
        expires_at=utcnow() + timedelta(hours=settings.auth_invitation_hours),
    )
    session.add(invitation)
    session.commit()
    session.refresh(invitation)
    return InvitationCreated(
        id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        expires_at=invitation.expires_at,
        token=token,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(
    principal: Principal = Depends(require_roles(UserRole.administrator)),
    session: Session = Depends(get_db),
) -> list[User]:
    return list(session.scalars(select(User).order_by(User.id)))
