"""Datasets and dataset membership (Sprint 3)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import (
    Principal,
    get_current_principal,
    get_db,
    probe_dep,
    require_roles,
    settings_dep,
    storage_dep,
)
from ..errors import ApiError
from ..models import Dataset, DatasetMembership, User, UserRole, Video
from ..schemas import (
    DatasetCreate,
    DatasetMemberAdd,
    DatasetMemberOut,
    DatasetOut,
    VideoOut,
)
from ..services.media import MediaProbe
from ..services.storage import LocalStorage
from .auth import normalise_email
from .videos import ingest_video

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _get_dataset_or_404(session: Session, dataset_id: int) -> Dataset:
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise ApiError(404, "DATASET_NOT_FOUND", f"dataset {dataset_id} does not exist")
    return dataset


def _is_member(session: Session, dataset_id: int, user_id: int | None) -> bool:
    if user_id is None:
        return False
    return (
        session.scalar(
            select(DatasetMembership).where(
                DatasetMembership.dataset_id == dataset_id,
                DatasetMembership.user_id == user_id,
            )
        )
        is not None
    )


def _require_access(session: Session, principal: Principal, dataset: Dataset) -> None:
    """Administrators see everything; everyone else needs a membership."""
    if principal.role == UserRole.administrator:
        return
    user_id = principal.user.id if principal.user is not None else None
    if not _is_member(session, dataset.id, user_id):
        # 404 rather than 403: do not reveal that an unassigned dataset exists.
        raise ApiError(404, "DATASET_NOT_FOUND", f"dataset {dataset.id} does not exist")


@router.post("", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def create_dataset(
    payload: DatasetCreate,
    request: Request,
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
) -> Dataset:
    dataset = Dataset(
        name=payload.name.strip(),
        description=payload.description.strip(),
        created_by_id=principal.user.id if principal.user is not None else None,
    )
    session.add(dataset)
    session.flush()
    # A Dataset Administrator owns access to what they create.
    if principal.user is not None and principal.role == UserRole.dataset_admin:
        session.add(DatasetMembership(dataset_id=dataset.id, user_id=principal.user.id))
    session.commit()
    session.refresh(dataset)
    return dataset


@router.get("", response_model=list[DatasetOut])
def list_datasets(
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[Dataset]:
    stmt = select(Dataset).order_by(Dataset.id.desc())
    if principal.role != UserRole.administrator:
        user_id = principal.user.id if principal.user is not None else None
        stmt = stmt.join(DatasetMembership).where(DatasetMembership.user_id == user_id)
    return list(session.scalars(stmt))


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> Dataset:
    dataset = _get_dataset_or_404(session, dataset_id)
    _require_access(session, principal, dataset)
    return dataset


@router.get("/{dataset_id}/members", response_model=list[DatasetMemberOut])
def list_members(
    dataset_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[DatasetMemberOut]:
    dataset = _get_dataset_or_404(session, dataset_id)
    _require_access(session, principal, dataset)
    rows = session.execute(
        select(DatasetMembership, User)
        .join(User, User.id == DatasetMembership.user_id)
        .where(DatasetMembership.dataset_id == dataset.id)
        .order_by(DatasetMembership.id)
    ).all()
    return [
        DatasetMemberOut(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post(
    "/{dataset_id}/members",
    response_model=DatasetMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    dataset_id: int,
    payload: DatasetMemberAdd,
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
) -> DatasetMemberOut:
    dataset = _get_dataset_or_404(session, dataset_id)
    _require_access(session, principal, dataset)

    user: User | None = None
    if payload.user_id is not None:
        user = session.get(User, payload.user_id)
    elif payload.email:
        user = session.scalar(select(User).where(User.email == normalise_email(payload.email)))
    else:
        raise ApiError(422, "MEMBER_TARGET_REQUIRED", "provide user_id or email")
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "no user matches that id or email")

    if principal.role == UserRole.dataset_admin and user.role != UserRole.annotator:
        raise ApiError(
            403,
            "FORBIDDEN",
            "dataset administrators can only add annotators",
        )
    if _is_member(session, dataset.id, user.id):
        raise ApiError(409, "MEMBER_EXISTS", "the user is already a member of this dataset")

    membership = DatasetMembership(dataset_id=dataset.id, user_id=user.id)
    session.add(membership)
    session.commit()
    session.refresh(membership)
    return DatasetMemberOut(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        created_at=membership.created_at,
    )


@router.post(
    "/{dataset_id}/videos",
    response_model=VideoOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_dataset_video(
    dataset_id: int,
    file: UploadFile = File(..., description="Single-view RGB video (mp4/mov/m4v/webm/mkv)"),
    principal: Principal = Depends(
        require_roles(UserRole.administrator, UserRole.dataset_admin)
    ),
    session: Session = Depends(get_db),
    storage: LocalStorage = Depends(storage_dep),
    probe: MediaProbe = Depends(probe_dep),
    settings: Settings = Depends(settings_dep),
) -> Video:
    dataset = _get_dataset_or_404(session, dataset_id)
    _require_access(session, principal, dataset)
    return await ingest_video(
        file,
        subdir=f"videos/dataset-{dataset.id}",
        project_id=None,
        dataset_id=dataset.id,
        session=session,
        storage=storage,
        probe=probe,
        settings=settings,
    )


@router.get("/{dataset_id}/videos", response_model=list[VideoOut])
def list_dataset_videos(
    dataset_id: int,
    principal: Principal = Depends(get_current_principal),
    session: Session = Depends(get_db),
) -> list[Video]:
    dataset = _get_dataset_or_404(session, dataset_id)
    _require_access(session, principal, dataset)
    return list(
        session.scalars(
            select(Video).where(Video.dataset_id == dataset_id).order_by(Video.id.desc())
        )
    )
