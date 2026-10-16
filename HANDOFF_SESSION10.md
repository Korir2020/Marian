# HANDOFF SESSION 10 (newest; older handoffs are stale)
STATE: full suite green (356 + new setup tests). B1 registration, B3 superadmin
review, B4 setup backend are BUILT. Teacher transfers built. Admin safety built.
NEXT, in order:
1. B2 applicant verification: no SMS provider, so use EMAIL OTP (decision pending).
   POST /api/school-registration/verify/, 10 min expiry, max 5 attempts, hashed code,
   never log codes, audit "school_admin_verified".
2. B5/B6/B7 frontend: setup wizard UI (reuse Setup.jsx), register-your-school
   screens, superadmin review screens. Use GET /api/setup/ and POST /api/setup/complete/.
3. Fix JWT SIGNING_KEY: it is 31 bytes, must be 32+; set via environment variable.
4. staticfiles/ dir warning: fix before deployment.
5. Later: school suspend, financial workflows, analytics + AI features, backups.
GIT: repo https://github.com/Korir2020/Marian (private). Push using `gh auth login`
(browser device login). Never paste tokens into chats.
RULES: inspect before editing, tests first, run full suite, commit by name.

## UPDATE 2026-10-16 (branch onboarding-ui, NOT pushed yet)
DONE (build passes, 383 backend tests pass):
- SchoolStatus.jsx: applicant "Check my application" screen (Landing button, App.jsx route, uses POST /api/school-registration/status/).
- RegistrationReview.jsx: status filter and email-verified badge.
- Backend GET/PATCH /api/school/profile/ (api/profile_views.py, 10 tests in api/test_school_profile.py). Non-deputy school admin edits own school only. Reason: approval never filled location or county, so setup checklist "profile" could never complete.
- SetupWizard.jsx: shown at top of the school admin Setup tab. Checklist, profile form, Finish setup (/api/setup/complete/).
- Label "Senior / Secondary" (stored value stays "secondary").
NOT DONE: browser check of the new screens, auto-open wizard on first login, "resend code" (needs a backend endpoint), needs_information status.
OPEN: DJANGO_EMAIL_* and DJANGO_FRONTEND_URL on Render (registration returns 503 without SMTP); replace DJANGO_SECRET_KEY; check Marian-app repo and branch.
DEPLOY: Render deploys from original main. Backup: ~/marian-backup-2026-10-15.dump (keep it).

## UPDATE 2 (same day, branch onboarding-ui)
DONE since the note above (390 tests pass, build passes):
- Auto-open: a non-deputy school admin with setup_complete false lands on the Setup tab when the URL has no tab (App.jsx).
- Resend code: POST /api/school-registration/resend/ (api/resend_views.py, 7 tests). 60 s cooldown, max 5 sends in total, reuses SchoolRegStatusThrottle, audit "school_reg_resent", 503 without email. Button with countdown in SchoolRegistration.jsx.
STILL NOT DONE: needs_information status (admin request-info action, applicant reply path); browser check of all new screens; SMTP (DJANGO_EMAIL_*, DJANGO_FRONTEND_URL) so registration and resend work live; replace DJANGO_SECRET_KEY; check Marian-app repo and branch.
