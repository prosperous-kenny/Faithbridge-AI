"""Dashboard routes: aggregate insights, impact report, and report export.

All three views are aggregates — counts, sums, and the Impact Score — so the
payloads are PII-free by construction (PRD §22). Faith leaders are scoped to
their own organization; a platform admin may read any one they name.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import CurrentUser
from app.core.rbac import Role, require_role
from app.db.session import get_session
from app.repositories import dashboard as dashboard_repo
from app.schemas.dashboard import (
    CommunityInsightsOut,
    ImpactReportOut,
    ReportMonth,
)
from app.schemas.impact import ImpactComponent
from app.services import impact as impact_service
from app.services.reporting import impact_export

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

DASHBOARD_ROLES = (Role.FAITH_LEADER, Role.ADMIN)


def _resolve_read_org(user, requested: int | None) -> int:
    """The organization an aggregate read applies to: leaders are locked to
    their own; an admin must name one because platform-wide insight blending
    would mix orgs' definitions of the Impact Score."""
    if user.organization_id is not None:
        if requested is not None and requested != user.organization_id:
            raise HTTPException(
                status_code=403,
                detail="You can only view dashboard data for your own organization",
            )
        return user.organization_id
    if requested is None:
        raise HTTPException(
            status_code=400, detail="organization_id is required for an admin read"
        )
    return requested


@router.get(
    "/stats",
    dependencies=[Depends(require_role(*DASHBOARD_ROLES))],
)
async def stats(session: SessionDep) -> dict:
    """Row counts per entity.

    Aggregates only, so there is no PII to gate. This endpoint is a platform
    operating figure for handlers; donor-facing insight endpoints are the
    ``community-insights`` route, which carries its own scope.
    """
    return await dashboard_repo.entity_counts(session)


@router.get(
    "/community-insights",
    response_model=CommunityInsightsOut,
    dependencies=[Depends(require_role(*DASHBOARD_ROLES))],
)
async def community_insights(
    session: SessionDep,
    user: CurrentUser,
    organization_id: Annotated[int | None, Query()] = None,
) -> CommunityInsightsOut:
    """Trends, high-need categories and donation effectiveness (PRD Use Case 3).

    Aggregates only — no beneficiary row is ever loaded — so the response is
    safe to render for anyone who passed the role+scope guard.
    """
    org = _resolve_read_org(user, organization_id)
    return await dashboard_repo.community_insights(session, organization_id=org)


@router.get(
    "/impact-report",
    response_model=ImpactReportOut,
    dependencies=[Depends(require_role(*DASHBOARD_ROLES))],
)
async def impact_report(
    session: SessionDep,
    user: CurrentUser,
    organization_id: Annotated[int | None, Query()] = None,
) -> ImpactReportOut:
    """The Community Impact Score plus its component and monthly breakdown.

    The score is reproducible from config alone (see ``impact_service``); the
    monthly rows are the materialised rollups, so this view never re-reads the
    raw event feed.
    """
    org = _resolve_read_org(user, organization_id)
    result = await impact_service.community_impact_score(session, organization_id=org)
    months = await dashboard_repo.impact_report_months(session, organization_id=org)

    components = {
        dimension: ImpactComponent(
            value=result["components"][dimension],
            weight=result["weights"][dimension],
            target=result["targets"][dimension],
        )
        for dimension in impact_service.DIMENSIONS
    }
    report_months = [
        ReportMonth(period_start=p, period_end=e, metric=m, total=t)
        for (p, e, m), t in sorted(months, key=lambda item: (item[0][0], item[0][1]))
    ]
    bounds = [(m.period_start, m.period_end) for m in report_months]
    return ImpactReportOut(
        organization_id=org,
        score=result["score"],
        components=components,
        months=report_months,
        period_start=min((b[0] for b in bounds), default=None),
        period_end=max((b[1] for b in bounds), default=None),
    )


@router.get(
    "/impact-report/export",
    dependencies=[Depends(require_role(*DASHBOARD_ROLES))],
)
async def export_impact_report(
    session: SessionDep,
    user: CurrentUser,
    file_format: Annotated[Literal["csv", "pdf"], Query(alias="format")] = "csv",
    organization_id: Annotated[int | None, Query()] = None,
) -> Response:
    """Download the impact report as CSV or PDF (PRD §23 reporting).

    Content is the same aggregate data as ``/impact-report``, rendered offline;
    export files never include beneficiary identifiers.
    """
    org = _resolve_read_org(user, organization_id)
    result = await impact_service.community_impact_score(session, organization_id=org)
    months = await dashboard_repo.impact_report_months(session, organization_id=org)
    components = {
        dimension: {
            "value": result["components"][dimension],
            "weight": result["weights"][dimension],
            "target": result["targets"][dimension],
        }
        for dimension in impact_service.DIMENSIONS
    }
    data = impact_export.report_data_from(
        organization_id=org,
        score=result["score"],
        components=components,
        months=months,
    )

    if file_format == "csv":
        media_type = "text/csv; charset=utf-8"
        filename = f"impact-report-org-{org}.csv"
        content = impact_export.render_csv(data)
    else:
        media_type = "application/pdf"
        filename = f"impact-report-org-{org}.pdf"
        content = impact_export.render_pdf(data)

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )