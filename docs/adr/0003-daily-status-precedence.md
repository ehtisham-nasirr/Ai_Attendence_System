# ADR-0003: Precedence between automatic daily statuses

**Status:** Accepted (owner decision, 2026-10-03)
**Requirements:** FR-22, FR-23, §10.3

## Context
A day has one status, but several automatic statuses can apply together (e.g. Late and Early Exit).

## Decision
Final automatic status precedence: **Missing Check-out > Half Day > Late > Early Exit > Present**. `late_minutes`, `early_minutes`, `worked_minutes` and `overtime_minutes` are always stored separately, so no information is lost. On top of that, §10.3 precedence is unchanged: manual approved correction > Leave > Holiday (and Weekly Off) > automatic.

The rule lives only in `backend/app/domain/attendance/rules.py`.
