# ADR-0004: Single-approver correction workflow

**Status:** Accepted (owner decision, 2026-10-03)
**Requirements:** FR-25, FR-26, §4, §21

## Decision
- An employee's correction request is decided by **any one** authorised approver: the employee's department manager, an HR Admin or a Super Admin (§4 "Approve manual corrections").
- A correction entered directly by HR, a department manager (own department) or a Super Admin (FR-25) is applied immediately and recorded as approved by its author, with a mandatory reason. The original values are kept in `attendance_corrections.old_value`.
- An approved correction locks the corrected field against later automatic updates.
