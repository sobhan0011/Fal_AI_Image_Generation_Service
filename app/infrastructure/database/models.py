from __future__ import annotations

from uuid import UUID, uuid4
from decimal import Decimal
from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Numeric, String, Text, func, Uuid

from ...models import GenerationStatus


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ai_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="user")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    aspect_ratio: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, native_enum=False),
        nullable=False,
        default=GenerationStatus.IN_QUEUE,
        index=True,
    )
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_refunded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    request_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship(back_populates="jobs")
