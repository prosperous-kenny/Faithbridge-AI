"""CSV and PDF rendering of the impact report (Phase 5 export).

Both formats are derived from the same report data object — score, component
breakdown, and the monthly rollup rows — so the JSON view, the CSV and the PDF
cannot drift apart. Only numbers and organization identifiers are rendered:
export files carry no beneficiary PII (PRD §22).
"""

from __future__ import annotations

import csv
import io
from datetime import datetime

from app.services.reporting.pdf import build_pdf


def _pad(text: str, width: int) -> str:
    plain = str(text)
    return plain[:width].ljust(width)


def _report_lines(report_data: dict) -> list[tuple[bool, str]]:
    lines: list[tuple[bool, str]] = [
        (True, "FaithBridge AI — Community Impact Report"),
        (False, f"Organization: {report_data['organization_id']}"),
        (False, ""),
        (True, f"Community Impact Score: {report_data['score']} / 100"),
        (False, ""),
        (True, "Components"),
        (True, f"{_pad('dimension', 18)}{_pad('value', 6)}{_pad('weight', 8)}{_pad('target', 8)}"),
    ]
    for dimension, component in report_data["components"].items():
        lines.append(
            (
                False,
                f"{_pad(dimension, 18)}{_pad(component['value'], 6)}{_pad(component['weight'], 8)}{_pad(component['target'], 8)}",
            )
        )
    lines += [
        (False, ""),
        (True, "Monthly totals"),
        (True, f"{_pad('period_start', 12)}{_pad('period_end', 12)}{_pad('metric', 22)}total"),
    ]
    for (period_start, period_end, metric), total in report_data["months"]:
        lines.append(
            (
                False,
                f"{_pad(period_start.date().isoformat(), 12)}{_pad(period_end.date().isoformat(), 12)}{_pad(metric, 22)}{total}",
            )
        )
    return lines


def render_csv(report_data: dict) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["FaithBridge AI Community Impact Report"])
    writer.writerow(["Organization", report_data["organization_id"]])
    writer.writerow(["Community Impact Score", report_data["score"]])
    writer.writerow([])
    writer.writerow(["Dimension", "Value", "Weight", "Target"])
    for dimension, component in report_data["components"].items():
        writer.writerow(
            [dimension, component["value"], component["weight"], component["target"]]
        )
    writer.writerow([])
    writer.writerow(["Period start", "Period end", "Metric", "Total"])
    for (period_start, period_end, metric), total in report_data["months"]:
        writer.writerow([period_start.isoformat(), period_end.isoformat(), metric, total])
    return buffer.getvalue().encode("utf-8")


def render_pdf(report_data: dict) -> bytes:
    header_block = 3  # title, org line, blank line that starts the score line
    return build_pdf(_report_lines(report_data), repeat_first=header_block)


def report_data_from(
    *,
    organization_id: int,
    score: int,
    components: dict[str, dict[str, float]],
    months: list[tuple[tuple[datetime, datetime, str], int]],
) -> dict:
    return {
        "organization_id": organization_id,
        "score": score,
        "components": components,
        "months": months,
    }