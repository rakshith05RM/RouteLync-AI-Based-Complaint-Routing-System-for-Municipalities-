"""
Adds every district of Karnataka as an Area, each with one catch-all ward, so a complaint can be filed from anywhere in the state.

    python manage.py seed_karnataka

Safe to run repeatedly. Real ward lists (for example the BBMP wards, or a city corporation's wards) are loaded separately with
`python manage.py import_wards wards.csv`. Nothing here is official ward data: the single "Whole district" ward is a placeholder
until you import real wards for that district.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from departments.models import Area, Ward

KARNATAKA_DISTRICTS = [
    "Bagalkot", "Ballari", "Belagavi", "Bengaluru Rural", "Bengaluru Urban", "Bidar", "Chamarajanagar", "Chikkaballapur",
    "Chikkamagaluru", "Chitradurga", "Dakshina Kannada", "Davanagere", "Dharwad", "Gadag", "Hassan", "Haveri", "Kalaburagi",
    "Kodagu", "Kolar", "Koppal", "Mandya", "Mysuru", "Raichur", "Ramanagara", "Shivamogga", "Tumakuru", "Udupi",
    "Uttara Kannada", "Vijayanagara", "Vijayapura", "Yadgir",
]


class Command(BaseCommand):
    help = "Add all 31 districts of Karnataka as areas (each with one placeholder ward)."

    @transaction.atomic
    def handle(self, *args, **opts):
        new_areas = new_wards = 0
        for name in KARNATAKA_DISTRICTS:
            area, created = Area.objects.get_or_create(name=name)
            new_areas += created
            if not area.wards.exists():
                Ward.objects.create(area=area, number=1, name="Whole district")
                new_wards += 1
        self.stdout.write(self.style.SUCCESS(
            f"Karnataka districts ready: {len(KARNATAKA_DISTRICTS)} total, {new_areas} added, {new_wards} placeholder ward(s) added."))
