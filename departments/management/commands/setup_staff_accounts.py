"""
Create (or update) the login accounts for every department and the administrator, in one fixed format:

    officer   <department>officer1@<domain>      password  <department>officer1@<first part of the domain>
    head      <department>head1@<domain>
    worker    <department>worker1@<domain>, <department>worker2@<domain>

    e.g. electricityofficer1@company.com / electricityofficer1@company

<department> is the department code in lower case without underscores (WATER_SUPPLY -> watersupply).

  * Accounts that already exist under the OLD demo names (officer.electricity@routelync.test, worker.ravi.kumar@...) are RENAMED
    in place, so their complaints, assignments and history are kept.
  * Running it again changes nothing, except that departments added later in the admin panel get their accounts.
    A password someone has changed is kept unless --reset-passwords is given.
  * The administrator is set only when --admin-email and --admin-password are both given (the password is never stored in the code).
  * --csv writes the credentials to a file for you (readable only by you). Keep that file out of the project folder and out of version control.

These passwords follow a guessable pattern on purpose (a college demonstration). Change them before any real use.
"""
import csv
import os
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import Role, User
from departments.management.commands.seed_master_data import STAFF, slug
from departments.models import Department, FieldWorkerProfile, OfficerProfile

LEGACY_ADMIN = "admin@routelync.test"
DOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$")


def dept_slug(dept) -> str:
    return re.sub(r"[^a-z0-9]", "", dept.code.lower())


def legacy_emails(dept) -> dict:
    """The demo addresses the old seed command used for this department."""
    if dept.code not in STAFF:
        return {}
    _, _, workers = STAFF[dept.code]
    key = dept.code.lower().split("_")[0]
    return {("officer", 1): f"officer.{key}@routelync.test", ("head", 1): f"head.{key}@routelync.test",
            **{("worker", i): f"worker.{slug(name)}@routelync.test" for i, name in enumerate(workers, start=1)}}


class Command(BaseCommand):
    help = "Create department officer/head/worker logins (and the administrator) in the standard format."

    def add_arguments(self, parser):
        parser.add_argument("--domain", default=None, help="Email domain (default: STAFF_EMAIL_DOMAIN, company.com)")
        parser.add_argument("--officers", type=int, default=1, help="Officers per department, besides the head (default 1)")
        parser.add_argument("--workers", type=int, default=2, help="Field workers per department (default 2)")
        parser.add_argument("--admin-email")
        parser.add_argument("--admin-password")
        parser.add_argument("--admin-name", default="Administrator")
        parser.add_argument("--csv", help="Write the credentials to this file")
        parser.add_argument("--reset-passwords", action="store_true", help="Set every password back to the standard one")
        parser.add_argument("--deactivate-legacy", action="store_true", help="Switch off old demo accounts that were not renamed")
        parser.add_argument("--allow-predictable-passwords", action="store_true", help="Required when DEBUG is False")
        parser.add_argument("--dry-run", action="store_true")

    # ------------------------------------------------------------------------------------------------
    def handle(self, *args, **opts):
        domain = (opts["domain"] or settings.STAFF_EMAIL_DOMAIN).strip().lower()
        if not DOMAIN_RE.match(domain):
            raise CommandError(f"'{domain}' is not a valid domain.")
        if opts["officers"] < 1 or opts["workers"] < 2:
            raise CommandError("Every department needs at least 1 officer and 2 workers.")
        if bool(opts["admin_email"]) != bool(opts["admin_password"]):
            raise CommandError("Give --admin-email and --admin-password together.")
        if not settings.DEBUG and not opts["allow_predictable_passwords"]:
            raise CommandError("These passwords follow a guessable pattern. With DJANGO_DEBUG=False add --allow-predictable-passwords "
                               "to confirm you understand, and change the passwords afterwards.")
        if not Department.objects.exists():
            raise CommandError("There are no departments yet. Run: python manage.py seed_master_data")

        self.domain, self.label = domain, domain.split(".")[0]
        self.opts, self.rows, self.legacy_used = opts, [], set()
        with transaction.atomic():
            if opts["admin_email"]:
                self._admin(opts["admin_email"].strip(), opts["admin_password"], opts["admin_name"])
            for dept in Department.objects.order_by("id"):
                self._department(dept)
            leftovers = self._legacy_leftovers()
            if opts["deactivate_legacy"]:
                for user in leftovers:
                    user.is_active = False
                    user.save(update_fields=["is_active", "updated_at"])
            if opts["dry_run"]:
                transaction.set_rollback(True)
        self._report(leftovers)
        if opts["csv"] and not opts["dry_run"]:
            self._write_csv(opts["csv"])

    # ------------------------------------------------------------------------------------------------
    def password_for(self, local: str) -> str:
        return f"{local}@{self.label}"

    def _record(self, dept, role, name, email, password, status):
        self.rows.append({"Department": dept.name if dept else "(all)", "Role": role, "Name": name, "Email (login)": email,
                          "Password": password, "Status": status})

    def _admin(self, email, password, name):
        target = User.objects.filter(email__iexact=email).first()
        status = "updated"
        if target is None:
            legacy = User.objects.filter(email__iexact=LEGACY_ADMIN).first()
            if legacy is not None:
                target, status = legacy, "renamed from the demo administrator"
                self.legacy_used.add(legacy.pk)
                target.email = email.lower()
            else:
                target, status = User(email=email.lower()), "created"
        target.full_name = target.full_name if status == "updated" and target.full_name else name
        target.role, target.is_staff, target.is_superuser = Role.ADMIN, True, True
        target.is_active, target.email_verified = True, True
        target.set_password(password)
        target.save()
        self._record(None, "Administrator", target.full_name, target.email, password, status)

    def _department(self, dept):
        index = dept.pk
        officer_name, head_name, worker_names = STAFF.get(dept.code, (None, None, []))
        plan = [("officer", n, Role.OFFICER) for n in range(1, self.opts["officers"] + 1)] + [("head", 1, Role.OFFICER)] + \
               [("worker", n, Role.FIELD_WORKER) for n in range(1, self.opts["workers"] + 1)]
        legacy = legacy_emails(dept)
        for kind, n, role in plan:
            local = f"{dept_slug(dept)}{kind}{n}"
            email = f"{local}@{self.domain}"
            if kind == "officer":
                name = officer_name if (n == 1 and officer_name) else f"{dept.name} Officer {n}"
            elif kind == "head":
                name = head_name or f"{dept.name} Head"
            else:
                name = worker_names[n - 1] if n <= len(worker_names) else f"{dept.name} Worker {n}"
            self._account(dept, kind, n, role, name, local, email, legacy.get((kind, n)), index)

    def _account(self, dept, kind, n, role, name, local, email, legacy_email, index):
        password = self.password_for(local)
        user = User.objects.filter(email__iexact=email).first()
        reset = self.opts["reset_passwords"]
        if user is not None:                                                    # already in the standard format
            if user.role != role:
                self.stdout.write(self.style.WARNING(f"  skipped {email}: it exists with a different role"))
                return
            profile_ok = self._ensure_profile(user, dept, kind, n, role)
            if reset:
                user.set_password(password)
            user.is_active, user.email_verified = True, True
            user.save()
            self._record(dept, kind.title(), user.full_name, email, password if reset else "(unchanged)", "reset" if reset else "already set up")
            return
        old = User.objects.filter(email__iexact=legacy_email).first() if legacy_email else None
        if old is not None and old.role == role:                                # an old demo account: rename it in place
            self.legacy_used.add(old.pk)
            old.email = email
            old.set_password(password)
            old.is_active, old.email_verified = True, True
            old.save()
            self._ensure_profile(old, dept, kind, n, role)
            self._record(dept, kind.title(), old.full_name, email, password, f"renamed from {legacy_email}")
            return
        user = User.objects.create_user(email=email, password=password, full_name=name, phone=self._phone(dept, kind, n), role=role,
                                        email_verified=True)
        self._ensure_profile(user, dept, kind, n, role)
        self._record(dept, kind.title(), name, email, password, "created")

    def _phone(self, dept, kind, n) -> str:
        offset = {"officer": n, "head": 10, "worker": 20 + n}[kind]
        return str(9100000000 + dept.pk * 100 + offset)

    def _ensure_profile(self, user, dept, kind, n, role):
        if role == Role.OFFICER:
            profile = OfficerProfile.objects.filter(user=user).first()
            if profile is None:
                OfficerProfile.objects.create(user=user, department=dept, is_department_head=(kind == "head"),
                                              designation="Department Head" if kind == "head" else "Assistant Engineer")
            return True
        profile = FieldWorkerProfile.objects.filter(user=user).first()
        if profile is None:
            number = n
            while FieldWorkerProfile.objects.filter(employee_code=f"{dept.code[:4]}-{number:03d}").exists():
                number += 1
            FieldWorkerProfile.objects.create(user=user, department=dept, employee_code=f"{dept.code[:4]}-{number:03d}")
        return True

    def _legacy_leftovers(self):
        emails = {e for dept in Department.objects.all() for e in legacy_emails(dept).values()} | {LEGACY_ADMIN}
        return [u for u in User.objects.filter(email__in=emails, is_active=True) if u.pk not in self.legacy_used]

    # ------------------------------------------------------------------------------------------------
    def _report(self, leftovers):
        counts = {}
        for r in self.rows:
            counts[r["Status"].split(" from")[0]] = counts.get(r["Status"].split(" from")[0], 0) + 1
        title = "DRY RUN (nothing was saved)" if self.opts["dry_run"] else "Staff accounts ready"
        self.stdout.write(self.style.SUCCESS(f"{title}: {len(self.rows)} accounts at @{self.domain} "
                                             + ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))))
        if leftovers:
            what = "switched off" if self.opts["deactivate_legacy"] else "still active (use --deactivate-legacy, or remove them in Admin > Users)"
            self.stdout.write(self.style.WARNING(f"Old demo accounts not renamed, {what}: " + ", ".join(sorted(u.email for u in leftovers))))
        self.stdout.write("Passwords follow a guessable pattern: change them before any real use.")

    def _write_csv(self, path):
        fields = ["Department", "Role", "Name", "Email (login)", "Password", "Status"]
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(self.rows)
        self.stdout.write(self.style.SUCCESS(f"Credentials written to {path} (keep this file private)."))
