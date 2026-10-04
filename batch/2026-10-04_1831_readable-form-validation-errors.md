# Batch: readable-form-validation-errors

**Date:** 2026-10-04 18:31
**Type:** bugfix
**Command Used:** commands/fix-bug.md
**Standards Referenced:** standards/04-rest-api-standards.md, standards/09-forms-errors-logging.md, standards/11-testing.md
**Requirements:** FR-25 (manual entry), NFR-14 (usability)

## Summary
In the owner's test, a manual attendance entry with check-in 11:20 PM and check-out 04:21 PM was rejected, but the portal only showed "Validation failed.". The real reason never reached the user. It is a form-level rule (check-out must be after check-in), so it is not attached to any one input.

## Changes Made
- **`backend/app/core/exceptions.py`:** validation messages drop Pydantic's "Value error, " prefix and start with a capital letter. For example, the error is now "Check-out must be after check-in".
- **`frontend/src/lib/forms.ts`:** `showFormError` still puts field errors under their inputs. Errors that match no input (for example `body`) are now shown in the toast, instead of the generic "Validation failed.".
- **Tests:**
  - backend: the manual entry with check-out before check-in returns 422 with `errors.body == ["Check-out must be after check-in"]`;
  - frontend: three tests for `showFormError` (field error under the input, unplaced error in the toast, fallback message).

## Files Changed
```
backend/app/core/exceptions.py
backend/tests/api/test_attendance_corrections.py
frontend/src/lib/forms.ts
frontend/src/lib/__tests__/forms.test.ts
```

## Database Changes
None.

## CPU / Performance Impact
N/A.

## Testing
- **Backend:** 156 passed; ruff and mypy are clean.
- **Frontend:** 59 tests passed; ESLint and `tsc` are clean.
- **Not verified:** the owner's laptop, which needs the backend and nginx images rebuilt.

## Notes
The entry itself was correctly rejected: 11:20 PM to 4:21 PM on the same day is impossible. The owner probably meant 11:20 AM. For night shifts the dialog has a "Check-out is on the next day" option.
