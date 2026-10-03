"""Report schemas (FR-30, FR-31)."""

import datetime as dt
from typing import Any, Literal

from facetrack_common.constants import AttendanceStatus, ReportType
from pydantic import Field

from app.schemas.common import ApiModel, InputModel

ColumnKind = Literal["date", "time", "minutes", "text", "code", "status", "bool", "count", "letter"]


class ReportColumn(ApiModel):
    key: str
    label: str
    kind: ColumnKind


class ReportSummaryItem(ApiModel):
    label: str
    value: int | float | str
    kind: ColumnKind = "count"


class ReportChartSeries(ApiModel):
    key: str
    label: str


class ReportChart(ApiModel):
    """Data for one chart: `x_key` on the x axis, one bar per series."""

    x_key: str
    series: list[ReportChartSeries]
    data: list[dict[str, Any]]


class ReportOut(ApiModel):
    report_type: ReportType
    title: str
    date_from: dt.date
    date_to: dt.date
    columns: list[ReportColumn]
    rows: list[dict[str, Any]] = Field(
        description="One object per row keyed by column key. Times are UTC ISO strings; minutes are integers."
    )
    total_rows: int
    truncated: bool = Field(
        description="True when the preview shows only the first rows; exports contain all"
    )
    summary: list[ReportSummaryItem]
    chart: ReportChart | None
    timezone: str


class ReportExportAccepted(ApiModel):
    job_id: str


class ReportFilters(InputModel):
    date_from: dt.date
    date_to: dt.date
    department_id: int | None = None
    employee_id: int | None = None
    status: AttendanceStatus | None = None
