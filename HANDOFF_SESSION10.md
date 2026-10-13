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
