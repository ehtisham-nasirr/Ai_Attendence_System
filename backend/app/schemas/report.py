"""Report schemas (FR-30, FR-31)."""

import datetime as dt
from typing import Any, Literal

from facetrack_common.constants import AttendanceStatus, ReportType
from pydantic import Field, field_validator, model_validator

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


# --- Excel export of a list view (§13 "export on every list", Q62) ---

SHEET_MAX_ROWS = 10_000  # the list screens export at most this many rows (Q42)
SHEET_MAX_COLUMNS = 64  # the monthly register has up to 31 day columns plus totals

Tone = Literal["ok", "warn", "bad", "info", "neutral", "leave"]


class SheetCell(InputModel):
    value: str | float | None = Field(default=None)
    tone: Tone | None = None

    @field_validator("value")
    @classmethod
    def _short(cls, value: str | float | None) -> str | float | None:
        if isinstance(value, str) and len(value) > 2_000:
            raise ValueError("A cell may hold at most 2,000 characters.")
        return value


class SheetExportIn(InputModel):
    """The rows a list screen shows, with each status cell's colour; rendered as an .xlsx file."""

    title: str = Field(min_length=1, max_length=80)
    file_name: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z0-9._ -]+$")
    columns: list[str] = Field(min_length=1, max_length=SHEET_MAX_COLUMNS)
    rows: list[list[SheetCell]] = Field(max_length=SHEET_MAX_ROWS)

    @model_validator(mode="after")
    def _rectangular(self) -> "SheetExportIn":
        if any(not 0 < len(c) <= 120 for c in self.columns):
            raise ValueError("Column headers must be 1 to 120 characters.")
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Every row must have one cell per column.")
        return self
