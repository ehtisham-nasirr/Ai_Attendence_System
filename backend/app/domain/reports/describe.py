"""Human-readable filter text for report headers and email subjects."""

from facetrack_common.models import Department, Employee
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.report import ReportFilters


async def filters_text(db: AsyncSession, filters: ReportFilters) -> str:
    parts: list[str] = []
    if filters.department_id:
        department = await db.get(Department, filters.department_id)
        parts.append(f"Department: {department.name if department else filters.department_id}")
    if filters.employee_id:
        employee = await db.get(Employee, filters.employee_id)
        parts.append(
            f"Employee: {employee.employee_code} {employee.full_name}"
            if employee
            else f"Employee: {filters.employee_id}"
        )
    if filters.status:
        parts.append(f"Status: {filters.status.value.replace('_', ' ')}")
    return "; ".join(parts)
