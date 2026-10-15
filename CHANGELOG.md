# School AI Platform — Changelog

## 2026-09-22

### Project Started
- Created the GitHub repository.
- Created AI_CONTEXT.md.
- Created ARCHITECTURE.md.
- Created DECISIONS.md.
- Established the initial project vision and architecture.

## B4 - Setup wizard backend
- GET /api/setup/ (checklist: profile, academic year, term, stream, subject)
- POST /api/setup/complete/ (full admins only, atomic, audited, idempotent)
- /api/auth/me/ now returns setup_complete
- api/setup_views.py, api/test_setup.py
