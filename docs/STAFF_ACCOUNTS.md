# Department logins (officers, heads, workers) and the administrator

## The format
| Account | Email (login) | Password |
|---|---|---|
| Officer | `<department>officer1@company.com` | `<department>officer1@company` |
| Department head | `<department>head1@company.com` | `<department>head1@company` |
| Field workers | `<department>worker1@company.com`, `<department>worker2@company.com` | `<department>worker1@company`, `...worker2@company` |

`<department>` is the department code in lower case without underscores. Examples:
`electricityofficer1@company.com` / `electricityofficer1@company`, `watersupplyworker2@company.com` / `watersupplyworker2@company`,
`civilregistrationhead1@company.com`. Every department has 1 officer, 1 head and 2 workers (`--officers` and `--workers` add more).
The department codes are: electricity, watersupply, sanitation, roads, parksgardens, health, townplanning, propertytax, tradelicence,
fire, animalcontrol, education, socialwelfare, civilregistration, trafficparking, environment, advertisements.

The email domain is the setting `STAFF_EMAIL_DOMAIN` (default `company.com`; I assumed `.com`). Change it in `.env` or with `--domain`.

## Create or update them
```bash
python manage.py setup_staff_accounts --admin-email <admin email> --admin-password "<admin password>" --csv staff_credentials.csv
```
- **Existing accounts are renamed in place** (the old demo logins such as `officer.electricity@routelync.test` and
  `worker.ravi.kumar@routelync.test`, and the demo administrator), so their complaints, assignments and history are kept. The old known
  demo password stops working.
- **Running it again changes nothing.** A password someone changed is kept unless you add `--reset-passwords`.
- **A department added later in Admin** gets its officer, head and two workers the next time you run the command.
- `--dry-run` shows what would happen; `--deactivate-legacy` switches off old demo accounts that could not be renamed.
- The administrator password is **not stored anywhere in the project**: you type it in the command. The login for the admin panel is the
  same email and password (it also opens the Django admin site at `/admin/`).
- `--csv` writes every login to a file that only you can read. Keep it out of the project folder and out of version control.

## Before real use
These passwords follow a pattern anyone can guess once they know the format, and the account lock-out (5 wrong attempts) is the only
protection. Change them (*Profile, Change password*) before the system holds real data. Also note that `company.com` is a real domain
owned by someone else: if email is ever configured, a "forgot password" message for these addresses would go to **that** company's
mail server, so use a domain you control (set `STAFF_EMAIL_DOMAIN`) before enabling real email.
