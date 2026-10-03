# ADR-0002: One response envelope (standards/04) for all lists

**Status:** Accepted (owner decision, 2026-10-03)
**Requirements:** §12.1 · **Standards:** 04

## Context
Requirements §12.1 says paginated lists return `data`, `meta`, `links`. standards/04 defines `{success, message, data, pagination: {page, page_size, total}}`.

## Decision
Use the standards/04 envelope everywhere, built with `ok()` / `created()` / `paginated()` / `error()` in `backend/app/core/responses.py`. The §12.1 wording is superseded. The internal engine API uses the same envelope.
