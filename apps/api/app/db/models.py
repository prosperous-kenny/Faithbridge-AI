from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Beneficiary(Base):
    __tablename__ = "beneficiaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    household_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    consented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AssistanceRequest(Base):
    __tablename__ = "assistance_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    urgency_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="low", server_default=text("'low'")
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="submitted",
        server_default=text("'submitted'"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Donation(Base):
    __tablename__ = "donations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    donor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    program_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default=text("'USD'")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pledged", server_default=text("'pledged'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Placement(Base):
    __tablename__ = "placements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(Integer, nullable=False)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    employer: Mapped[str] = mapped_column(String(200), nullable=False)
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    placed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ImpactEvent(Base):
    __tablename__ = "impact_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())