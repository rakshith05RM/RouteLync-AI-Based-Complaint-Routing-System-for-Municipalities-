# Security and privacy

## Who can see what
| Information | Citizen | Field worker | Department officer | Administrator |
|---|---|---|---|---|
| Own complaints | yes | n/a | n/a | n/a |
| Other citizens' complaints | no (404) | no | no | all |
| Complaints of own department | n/a | only assigned jobs | all of the department | all |
| Another department's complaints | no | no (404) | no (404) | all |
| Citizen name and mobile | own | on assigned jobs | on department complaints | yes |
| Citizen email | own | no | no | yes |
| Priority, SLA, AI details, internal remarks | no | priority and deadline only | yes | yes |
| Complaint photos | own (the proof-of-fix photo only after an officer has verified the work) | assigned jobs | department | yes |
| Map data | n/a | own job | no citizen details in map data | n/a |
| Audit log, user list, model controls | no | no | no | yes |

## Controls and where they live
| Requirement | Implementation | Evidence |
|---|---|---|
| Password hashing | PBKDF2 via `set_password` | `accounts/tests/test_user_model.py` |
| Password strength, duplicate email | validators in the registration form | `test_registration.py` |
| CSRF | middleware, tokens in every form, friendly failure page | `core/tests_security.py` |
| Session safety | HttpOnly, SameSite, secure cookies in production | settings, deploy check |
| Brute force | lockout after 5 failed logins; registration and password-reset limits | `test_login.py`, `ThrottleTests` |
| Authorization | role mixins, department scoping, `complaints_visible_to`, route matrix test | `AccessMatrixTests` |
| Object-level access | other people's complaints return 404 (no ID enumeration) | access tests in every module |
| File upload safety | real content check with Pillow, size/dimension limits, extension must match, random file names, metadata stripped by re-encoding, no direct `/media/` serving | `test_validators.py`, `test_submission.py` |
| XSS | template auto-escaping, DOM text methods in map popups, Content-Security-Policy without inline scripts | `HeaderTests` |
| SQL injection | ORM only; injection-style input tested | `test_officer_dashboard.py` |
| Secrets | environment variables; the app refuses to start in production without a key | `DeploymentChecklistTests` |
| Audit | status changes, corrections, model training, imports, sign-ins | `adminpanel/tests/test_audit.py` |
| Error handling | friendly 400/403/404/500 pages, technical detail only in logs | `ErrorPageTests` |
| Data integrity | foreign keys, check constraints, transactions | model tests, MySQL run |

## Added with email verification and location search
| Requirement | Implementation | Evidence |
|---|---|---|
| Email ownership proved before sign-in | 6-digit code, keyed hash stored, 10-minute expiry, one use, 5 guesses, resend cooldown and hourly cap, per-address attempt limit | `accounts/tests/test_email_verification.py` |
| No account enumeration | registering an existing address and asking for a reset give the same pages as new/unknown ones | `test_registration.py`, `PasswordResetEmailTests` |
| Codes and reset links not logged | asserted by test | `test_codes_are_never_written_to_the_logs` |
| Honest failure reporting | a failed email is shown as failed, with a one-click retry | `DeliveryFailureTests` |
| Location cannot be forged | address, place and coordinates bound by a signed, expiring, per-user token; service area enforced; API key stays on the server | `complaints/tests/test_location.py`, `core/tests_geo.py` |
| XSS from search results | result text inserted with `textContent` only | test checks the script for unsafe calls; browser run |

## Known limits
- Rate-limit counters use local memory; use a shared cache (Redis) in a multi-process deployment.
- The Content-Security-Policy allows inline `style` attributes; the Django admin site at `/admin/` is excluded from it.
- No email or SMS; password-reset email uses the console backend until SMTP is configured.
- Passwords chosen by an administrator for new staff are temporary; there is no forced-change-on-first-login yet.
