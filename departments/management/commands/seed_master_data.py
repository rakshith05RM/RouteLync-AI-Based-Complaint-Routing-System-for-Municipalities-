"""
Loads master data: departments, sample areas/wards, example SLA hours, and (optionally) demo users.

    python manage.py seed_master_data
    python manage.py seed_master_data --demo-users --password "<choose a password>"

Safe to run repeatedly (idempotent). Demo users are created only when DEBUG=True and the
password is supplied on the command line, so no credential is hard-coded in the project.
All data below is SAMPLE data for demonstration; ward numbers are illustrative, not official.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import CitizenProfile, Role, User
from departments.models import Area, Department, FieldWorkerProfile, OfficerProfile, SLAConfiguration, Ward
from departments.services import DEFAULT_SLA_HOURS

DEPARTMENTS = [
    ("Electricity", "ELECTRICITY", "Streetlights, power lines, transformers, outages"),
    ("Water Supply", "WATER_SUPPLY", "Taps, pipelines, leakages, water quality"),
    ("Sanitation", "SANITATION", "Garbage, drains, sewage, public cleanliness"),
    ("Roads", "ROADS", "Potholes, footpaths, manholes, road damage"),
    ("Parks & Gardens", "PARKS_GARDENS", "Trees, parks, playgrounds, garden upkeep"),
    ("Public Health", "HEALTH", "Health centres, vaccination, fogging, outbreaks, food safety"),
    ("Town Planning & Buildings", "TOWN_PLANNING", "Illegal construction, plan approval, unsafe buildings, encroachment"),
    ("Property Tax & Revenue", "PROPERTY_TAX", "Tax bills, assessment, khata, receipts"),
    ("Trade Licence & Markets", "TRADE_LICENCE", "Trade licences, vendors, municipal markets"),
    ("Fire & Emergency", "FIRE", "Fire hazards, hydrants, rescue"),
    ("Animal Control", "ANIMAL_CONTROL", "Stray dogs, cattle, monkeys, dog bites, sterilisation"),
    ("Municipal Education", "EDUCATION", "Municipal schools and anganwadis"),
    ("Social Welfare", "SOCIAL_WELFARE", "Pensions, welfare schemes, scholarships, shelters"),
    ("Birth, Death & Marriage Registration", "CIVIL_REGISTRATION", "Birth, death and marriage certificates and records"),
    ("Traffic & Parking", "TRAFFIC_PARKING", "Signals, parking, bus shelters, traffic jams"),
    ("Environment & Lakes", "ENVIRONMENT", "Lake, air and noise pollution, factory smoke and effluent"),
    ("Advertisements & Hoardings", "ADVERTISEMENTS", "Illegal hoardings, flex banners, posters"),
]

AREAS = {
    "Jayanagar": [153, 154, 155],
    "Indiranagar": [80, 81, 82],
    "Whitefield": [84, 85, 86],
    "Rajajinagar": [98, 99, 100],
}

# code -> (officer, head, [workers])
STAFF = {
    "ELECTRICITY": ("Meera Nair", "Gopal Hegde", ["Ravi Kumar", "Manoj Shetty"]),
    "WATER_SUPPLY": ("Suresh Gowda", "Kavitha Rao", ["Lakshmi Devi", "Imran Pasha"]),
    "SANITATION": ("Anita Desai", "Raghu Prasad", ["Savitha Reddy", "Dinesh Kumar"]),
    "ROADS": ("Vikram Shetty", "Nandini Iyer", ["Prakash Murthy", "Harish Babu"]),
    "PARKS_GARDENS": ("Shobha Naik", "Mahesh Gowda", ["Bharath Kumar", "Nagaraj Patil"]),
    "HEALTH": ("Rekha Menon", "Ashok Pai", ["Latha Shetty", "Irfan Khan"]),
    "TOWN_PLANNING": ("Sanjay Kulkarni", "Padma Hegde", ["Deepak Rao", "Mohan Das"]),
    "PROPERTY_TAX": ("Usha Bhat", "Venkatesh Murthy", ["Kiran Joshi", "Shilpa Nayak"]),
    "TRADE_LICENCE": ("Farooq Ahmed", "Geetha Krishnan", ["Ramesh Babu", "Sunitha Rao"]),
    "FIRE": ("Ravi Teja", "Anand Patil", ["Suresh Naik", "Vinod Kumar"]),
    "ANIMAL_CONTROL": ("Meenakshi Rao", "Joseph Mathew", ["Ganesh Poojary", "Sridhar Naik"]),
    "EDUCATION": ("Kamala Devi", "Narayan Shastry", ["Poornima Hegde", "Basavaraj Patil"]),
    "SOCIAL_WELFARE": ("Jyothi Kamath", "Syed Rahman", ["Pushpa Latha", "Chandrashekar Gowda"]),
    "CIVIL_REGISTRATION": ("Nirmala Shenoy", "Prakash Rao", ["Manjula Devi", "Ismail Sheikh"]),
    "TRAFFIC_PARKING": ("Harsha Vardhan", "Leela Bai", ["Santosh Kumar", "Rohit Shetty"]),
    "ENVIRONMENT": ("Aparna Reddy", "Subramanya Iyer", ["Tejas Gowda", "Fathima Begum"]),
    "ADVERTISEMENTS": ("Girish Nayak", "Revathi Menon", ["Yogesh Kumar", "Zainab Khan"]),
}


def slug(name: str) -> str:
    return name.lower().replace(" ", ".")


class Command(BaseCommand):
    help = "Seed departments, areas, wards, SLA defaults and optional demo users."

    def add_arguments(self, parser):
        parser.add_argument("--demo-users", action="store_true", help="Also create demo staff and a demo citizen (DEBUG only).")
        parser.add_argument("--password", help="Password for demo users (required with --demo-users).")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["demo_users"]:
            if not settings.DEBUG:
                raise CommandError("Demo users can only be created when DJANGO_DEBUG=True.")
            if not opts["password"]:
                raise CommandError("--password is required with --demo-users.")

        for name, code, desc in DEPARTMENTS:
            Department.objects.get_or_create(code=code, defaults={"name": name, "description": desc})

        for area_name, wards in AREAS.items():
            area, _ = Area.objects.get_or_create(
                name=area_name, defaults={"service_district": Area.ServiceDistrict.BENGALURU_URBAN})
            if not area.service_district:
                area.service_district = Area.ServiceDistrict.BENGALURU_URBAN
                area.save(update_fields=["service_district"])
            for number in wards:
                Ward.objects.get_or_create(area=area, number=number)

        for priority, hours in DEFAULT_SLA_HOURS.items():
            SLAConfiguration.objects.get_or_create(priority=priority, defaults={"hours": hours})

        self.stdout.write(self.style.SUCCESS(
            f"Master data ready: {Department.objects.count()} departments, {Area.objects.count()} areas, "
            f"{Ward.objects.count()} wards, {SLAConfiguration.objects.count()} SLA rules."))

        if opts["demo_users"]:
            self._demo_users(opts["password"])

    def _make_user(self, email, name, role, password, phone, **extra):
        user, created = User.objects.get_or_create(
            email=email, defaults={"full_name": name, "role": role, "phone": phone, "email_verified": True, **extra})
        if created:
            user.set_password(password)
            user.save()
        return user

    def _demo_users(self, password):
        n = 0
        admin = self._make_user("admin@routelync.test", "Demo Administrator", Role.ADMIN, password,
                                "9000000000", is_staff=True, is_superuser=True)
        citizen = self._make_user("citizen@routelync.test", "Demo Citizen", Role.CITIZEN, password, "9876543210")
        CitizenProfile.objects.get_or_create(user=citizen, defaults={"address": "Jayanagar, Bengaluru (demo)"})

        for dept in Department.objects.filter(code__in=STAFF).order_by("id"):
            officer_name, head_name, workers = STAFF[dept.code]
            key = dept.code.lower().split("_")[0]
            for who, name, is_head in (("officer", officer_name, False), ("head", head_name, True)):
                n += 1
                u = self._make_user(f"{who}.{key}@routelync.test", name, Role.OFFICER, password, f"9000001{n:03d}")
                OfficerProfile.objects.get_or_create(user=u, defaults={
                    "department": dept, "is_department_head": is_head,
                    "designation": "Department Head" if is_head else "Assistant Engineer"})
            for i, name in enumerate(workers, start=1):
                n += 1
                u = self._make_user(f"worker.{slug(name)}@routelync.test", name, Role.FIELD_WORKER, password, f"9000002{n:03d}")
                FieldWorkerProfile.objects.get_or_create(user=u, defaults={
                    "department": dept, "employee_code": f"{dept.code[:4]}-{i:03d}"})
        self.stdout.write(self.style.SUCCESS(
            f"Demo users ready (admin: {admin.email}, citizen: {citizen.email}; "
            f"officers: officer.<dept>@routelync.test; workers: worker.<name>@routelync.test)."))
