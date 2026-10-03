# Python Standards

Applies to `common/`, `engine/` and `backend/`.

## Version and Style

- **Python 3.12** for all three packages.
- Follow PEP 8, enforced by **Ruff** (lint + format). Code must pass `ruff check` and `ruff format --check` in CI.
- **Type hints everywhere**, checked by **mypy** in strict mode for `common/` and `backend/`, and for engine modules outside tight numeric loops.

```python
def compute_late_minutes(check_in: datetime, shift_start: datetime, grace: timedelta) -> int:
    """Minutes late after the grace period (FR-22); 0 if on time."""
    late = check_in - (shift_start + grace)
    return max(0, int(late.total_seconds() // 60))
```

- Each function has one clear responsibility. If a function needs a paragraph to explain, split it.
- Use `datetime` objects with timezone info (`zoneinfo`) — never naive datetimes. Store and compare in UTC; convert to the location timezone only for business-date calculations.
- Use `Enum` / `StrEnum` from `common/constants.py` for roles, statuses and camera modes — no magic strings.

## Dependency Management

- Each package has a `pyproject.toml`; dependencies are pinned with a lock file (`uv.lock`). This is the single source of truth.
- Before adding a package, check whether the sanctioned stack (CLAUDE.md §1.2) already provides it.
- When adding a dependency, consider maintenance status, security history, licence (must allow internal commercial use), and whether it pulls in GPU/CUDA packages — **CPU-only builds are mandatory** (e.g. `onnxruntime`, not `onnxruntime-gpu`).
