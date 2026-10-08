from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    org_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    programs: Mapped[list["Program"]] = relationship(back_populates="organization")
    beneficiaries: Mapped[list["Beneficiary"]] = relationship(back_populates="organization")
    impact_events: Mapped[list["ImpactEvent"]] = relationship(back_populates="organization")
    impact_config: Mapped["OrgImpactConfig | None"] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_organization_id", "organization_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: a platform admin may have no organization. ondelete=SET NULL
    # so removing an org de-scopes its users rather than deleting them.
    organization_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    # Local-mode credential. NULL for accounts that authenticate through the
    # OIDC provider instead: the API must never hold a password it does not
    # itself check, so this column is only populated when AUTH_MODE=local.
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Disabling an account is not the same as deleting it: audit rows and
    # donations must keep pointing at a real user (PRD §22 immutable trail),
    # so revocation is a flag, not a foreign-key break.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization | None"] = relationship(back_populates="users")
    beneficiary: Mapped["Beneficiary | None"] = relationship(back_populates="user")
    preference: Mapped["DonorPreference | None"] = relationship(back_populates="donor")


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (Index("ix_programs_organization_id", "organization_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Phase 3 matching fields. All nullable: a matching run must still be able
    # to rank programs that predate the richer profile or that kept their
    # description off the public directory.
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    budget_needed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A deactivated program is retired from donor matching and the public list,
    # without deleting the row (donations keep pointing at it, PRD §8).
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="programs")
    donations: Mapped[list["Donation"]] = relationship(back_populates="program")


class DonorPreference(Base):
    __tablename__ = "donor_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # One preference row per donor (PRD §20 single role per user). CASCADE: a
    # donor account removal drops its preferences, which own no financial
    # history of their own.
    donor_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # The donor's stated causes (PRD Use Case 2), stored as a Postgres array of
    # category slugs. Empty means "any cause".
    causes: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default=text("'{}'")
    )
    budget: Mapped[float | None] = mapped_column(Float, nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    donor: Mapped["User"] = relationship(back_populates="preference")


class Beneficiary(Base):
    __tablename__ = "beneficiaries"
    __table_args__ = (
        Index("ix_beneficiaries_organization_id", "organization_id"),
        Index("ix_beneficiaries_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # Optional: not every beneficiary has a portal login.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    household_size: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    consented_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="beneficiaries")
    user: Mapped["User | None"] = relationship(back_populates="beneficiary")
    requests: Mapped[list["AssistanceRequest"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )
    placements: Mapped[list["Placement"]] = relationship(
        back_populates="beneficiary", cascade="all, delete-orphan"
    )


class AssistanceRequest(Base):
    __tablename__ = "assistance_requests"
    __table_args__ = (
        Index("ix_assistance_requests_beneficiary_id", "beneficiary_id"),
        Index("ix_assistance_requests_organization_id", "organization_id"),
        Index("ix_assistance_requests_priority", "priority"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("beneficiaries.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
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

    beneficiary: Mapped["Beneficiary"] = relationship(back_populates="requests")


class Donation(Base):
    __tablename__ = "donations"
    __table_args__ = (
        Index("ix_donations_donor_id", "donor_id"),
        Index("ix_donations_organization_id", "organization_id"),
        Index("ix_donations_program_id", "program_id"),
        Index("ix_donations_allocated_to_beneficiary_id", "allocated_to_beneficiary_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # A donor is a user. No ondelete: a donation is financial history and must
    # never disappear because a user row was removed (PRD §8 ledger integrity).
    donor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    program_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("programs.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD", server_default=text("'USD'")
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pledged",
        server_default=text("'pledged'"),
    )
    # Phase 4 lifecycle timestamps. Set when the status is reached; NULL
    # until then, so a ledger row records *when* money moved, not just that it
    # did. ``allocated_to_beneficiary_id`` is SET NULL because a donation is
    # financial history that must survive the beneficiary row (PRD §8).
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    distributed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    allocated_to_beneficiary_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("beneficiaries.id", ondelete="SET NULL"), nullable=True
    )
    # Provider-side transaction id captured when a pledge is paid (Phase 6).
    # Kept so reconciliation and the audit trail can tie the ledger row to the
    # payment provider; ephemeral providers (mocks) still write a reference so
    # the contract is exercised everywhere.
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    donor: Mapped["User"] = relationship()
    program: Mapped["Program | None"] = relationship(back_populates="donations")
    allocated_beneficiary: Mapped["Beneficiary | None"] = relationship()


class Placement(Base):
    """An employment/mentorship outcome (PRD §14 Employment Empowerment Module).

    ``skills`` are the job-seeker's skills at placement, kept on the row so the
    job matching service can rank future roles and so successful matches are
    reproducible. ``mentor_user_id`` links a FaithBridge user offering
    mentorship; it is SET NULL because mentorship is a relationship, not a
    financial record, and must not orphan on user removal.
    """

    __tablename__ = "placements"
    __table_args__ = (
        Index("ix_placements_beneficiary_id", "beneficiary_id"),
        Index("ix_placements_organization_id", "organization_id"),
        Index("ix_placements_mentor_user_id", "mentor_user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beneficiary_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("beneficiaries.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employer: Mapped[str] = mapped_column(String(200), nullable=False)
    role_title: Mapped[str] = mapped_column(String(200), nullable=False)
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default=text("'{}'")
    )
    # Progress of the placement: placed → started → graduated. Non-terminal
    # rows are the pool the job matching service scores.
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="placed",
        server_default=text("'placed'"),
    )
    mentor_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    placed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    beneficiary: Mapped["Beneficiary"] = relationship(back_populates="placements")
    mentor: Mapped["User | None"] = relationship(foreign_keys=[mentor_user_id])


class ImpactEvent(Base):
    __tablename__ = "impact_events"
    __table_args__ = (
        Index("ix_impact_events_organization_id", "organization_id"),
        Index("ix_impact_events_metric", "metric"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="impact_events")


class OrgImpactConfig(Base):
    """Per-organization weights and targets for the Community Impact Score
    (PRD §15: "weights configurable per organization").

    One row per organization. When no row exists, the service uses the PRD
    baseline weights and unit targets, so the score is *reproducible from
    config alone*: a caller can compute it by hand from the config row (or its
    absence) plus the impact_events feed.
    """

    __tablename__ = "org_impact_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # PRD §15 baseline weights (sum to 1.0). Each dimension's raw event total
    # is capped at its target to map 0..target -> 0..100 before weighting.
    families_weight: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.25")
    )
    education_weight: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.20")
    )
    employment_weight: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.20")
    )
    food_security_weight: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.20")
    )
    healthcare_weight: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("0.15")
    )
    families_target: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("100")
    )
    education_target: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("100")
    )
    employment_target: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("100")
    )
    food_security_target: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("100")
    )
    healthcare_target: Mapped[float] = mapped_column(
        Float, nullable=False, server_default=text("100")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="impact_config")


class ImpactRollup(Base):
    """Materialised per-organisation period totals over impact_events.

    Derived, replaceable aggregation: the worker deletes and re-inserts the
    rows for the period it recomputes. ``impact_events`` itself stays
    append-only; this table exists so dashboards and the monthly report do not
    re-scan the raw feed on every render.
    """

    __tablename__ = "impact_rollups"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "period_start",
            "period_end",
            "metric",
            name="ix_impact_rollups_org_period_metric",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    metric: Mapped[str] = mapped_column(String(50), nullable=False)
    total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped["Organization"] = relationship()


class DeletionRequest(Base):
    """A data-deletion request (PRD §22): beneficiaries may request deletion.

    ``impact_events``, ``donations`` and ``audit_logs`` are append-only by
    design, so "deletion" here is a governed workflow, not a raw DELETE: the
    request is recorded, reviewed, and acted on by an administrator who
    anonymises the linked rows that the tamper-evident trail must keep.
    """

    __tablename__ = "deletion_requests"
    __table_args__ = (
        Index("ix_deletion_requests_organization_id", "organization_id"),
        Index("ix_deletion_requests_beneficiary_id", "beneficiary_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # SET NULL like audit_logs: the request must outlive the rows it concerns.
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    requester_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    beneficiary_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("beneficiaries.id", ondelete="SET NULL"), nullable=True
    )
    # What is being deleted: beneficiary records, donor history, or the account.
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class SentMessage(Base):
    """Append-only record of an outbound channel message (WhatsApp, …).

    The message itself is sent by a channel adapter behind the messaging
    provider interface; this row keeps the auditable trail of *what the
    platform asked a provider to deliver* (PRD §22). ``organization_id`` is
    SET NULL so the trail outlives the org. Phone numbers are masked at the
    API boundary.
    """

    __tablename__ = "sent_messages"
    __table_args__ = (Index("ix_sent_messages_organization_id", "organization_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    recipient_phone: Mapped[str] = mapped_column(String(30), nullable=False)
    template: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="queued",
        server_default=text("'queued'"),
    )
    provider_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_organization_id", "organization_id"),
        Index("ix_audit_logs_actor_id", "actor_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Both nullable and SET NULL: an audit row must outlive the org and the
    # actor it records (PRD §22 tamper-evident trail).
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Case-handler note attached to the action (e.g. a status transition).
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    actor: Mapped["User | None"] = relationship()


class Volunteer(Base):
    """A volunteer profile: skills plus when they can work (PRD §14).

    One row per user; re-registering updates the profile instead of creating a
    second one (``ix_volunteers_user_id`` is unique). CASCADE on both FKs
    because the profile is owned data: it is meaningless without the user who
    filled it in or the organization that fields it.
    """

    __tablename__ = "volunteers"
    __table_args__ = (
        UniqueConstraint("user_id", name="ix_volunteers_user_id"),
        Index("ix_volunteers_organization_id", "organization_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    skills: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default=text("'{}'")
    )
    # Availability slot tokens, e.g. weekend_evening (see services/volunteering).
    availability: Mapped[list[str]] = mapped_column(
        ARRAY(String(30)), nullable=False, server_default=text("'{}'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship()
    organization: Mapped["Organization"] = relationship()


class FraudFlag(Base):
    """A pending abuse signal awaiting human review (PRD §22).

    Screening never blocks a submission — a false positive that hid a real
    need would be worse than a review — so this row is the record of *why*
    something looked wrong, for a leader to confirm or dismiss. Like the
    audit trail, it outlives the rows it concerns: SET NULL on both FKs.
    """

    __tablename__ = "fraud_flags"
    __table_args__ = (
        Index("ix_fraud_flags_organization_id", "organization_id"),
        Index("ix_fraud_flags_request_id", "request_id"),
        Index("ix_fraud_flags_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("assistance_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Rule name (duplicate_request, submission_burst) and reviewer status:
    # open → confirmed / dismissed, with open allowing a re-open.
    rule: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium", server_default=text("'medium'")
    )
    detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default=text("'open'")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    request: Mapped["AssistanceRequest | None"] = relationship()
