"""
One command that prepares a complete demonstration environment (development only):

    python manage.py setup_demo --password "<choose a password>"

It loads master data and demo accounts, imports the training data, trains and activates a model, then
submits sample complaints through the REAL services (so the AI routing, priorities, SLA deadlines and
duplicate flags are genuine model output, not hard-coded) and moves a few of them along the workflow.
The scenario complaint from the demo script (streetlight, ward 154) is deliberately NOT created, so it
can be submitted live.
"""
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CitizenProfile, Role, User
from complaints.models import Complaint
from complaints.services import (add_remark, assign_worker, complete_work, confirm_resolution, review_resolution,
                                 route_complaint, start_work, submit_complaint, submit_feedback)
from departments.models import Department, Ward
from ml_engine.models import MLModel

CITIZENS = [("Asha Rao", "citizen@routelync.test", "9876543210"), ("Ravi Shankar", "ravi.shankar@routelync.test", "9812300001"),
            ("Lakshmi Iyer", "lakshmi.iyer@routelync.test", "9812300002"), ("Imran Pasha", "imran.pasha@routelync.test", "9812300003"),
            ("Divya Menon", "divya.menon@routelync.test", "9812300004")]

# (citizen index, ward, street, landmark, lat, lng, title, description, final step)
SAMPLES = [
    (1, 154, "4th Main Road", "Near Metro station", 12.9250, 77.5938, "Large pothole on the road", "There is a very large pothole in the middle of 4th Main Road near the metro station and bikes are skidding.", "pending"),
    (2, 154, "4th Main Road", "Near Metro station", 12.9252, 77.5941, "Huge pothole on 4th Main Road", "A huge pothole has formed on 4th Main Road near the metro station and many bikes are skidding there.", "pending"),
    (3, 153, "5th Cross", "Opposite school", 12.9302, 77.5841, "Garbage not collected", "Garbage has not been collected from our street for a week and it smells terrible.", "closed"),
    (4, 155, "Main Street", "", 12.9188, 77.5897, "No water supply", "There is no water supply in our lane for the last three days and nobody has come to check.", "in_progress"),
    (1, 153, "Temple Road", "Behind temple", 12.9330, 77.5800, "Transformer making loud noise", "The transformer behind the temple is making a loud humming noise and the lights flicker.", "assigned"),
    (2, 155, "Market Road", "Near market", 12.9199, 77.5880, "Live wire hanging low", "A live electric wire is hanging low near the market and children play there.", "resolved"),
    (3, 80, "100 Feet Road", "", 12.9784, 77.6408, "Drain blocked", "The drain in front of the shop is blocked and dirty water is overflowing onto the road.", "pending"),
    (4, 84, "Whitefield Main Road", "Near bus stop", 12.9698, 77.7500, "Manhole cover missing", "The manhole cover is missing on the road near the bus stop and it is dangerous.", "pending"),
    (0, 98, "Dr Rajkumar Road", "", 12.9910, 77.5550, "Dirty water from the tap", "Dirty water is coming from the tap in our building since yesterday morning.", "pending"),
    (1, 99, "Chord Road", "", 12.9930, 77.5470, "Streetlights off in the lane", "None of the street lights in our lane turn on in the evening since last week.", "in_progress"),
    (2, 100, "West Park Road", "Community park", 12.9960, 77.5520, "Park lights not working", "Park lights are not working after sunset and the walking track is very dark.", "pending"),
    (3, 81, "CMH Road", "", 12.9780, 77.6400, "Broken footpath", "The footpath is broken and people trip over the loose tiles near the corner.", "closed"),
    (4, 154, "4th Main Road", "", None, None, "Quantum flux capacitor anomaly", "Quantum entanglement flux capacitor variance detected nearby recently.", "unrouted"),
]


def demo_proof_photo():
    """A generated stand-in picture (no real photograph is included with the project)."""
    img = Image.new("RGB", (800, 520), (92, 140, 110))
    draw = ImageDraw.Draw(img)
    draw.polygon([(0, 520), (800, 520), (560, 300), (240, 300)], fill=(70, 74, 80))
    draw.rectangle([392, 130, 408, 300], fill=(210, 210, 210))
    draw.ellipse([374, 100, 426, 140], fill=(255, 224, 120))
    buffer = io.BytesIO()
    img.save(buffer, "JPEG", quality=85)
    return SimpleUploadedFile("completed-work.jpg", buffer.getvalue(), content_type="image/jpeg")


class Command(BaseCommand):
    help = "Prepare a complete demonstration environment (development only)."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for every demo account")
        parser.add_argument("--skip-training", action="store_true", help="Reuse the active model if there is one")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("setup_demo only runs with DJANGO_DEBUG=True.")
        out = io.StringIO()
        call_command("seed_master_data", "--demo-users", "--password", opts["password"], stdout=out)
        for name, email, phone in CITIZENS[1:]:
            user, created = User.objects.get_or_create(email=email, defaults={"full_name": name, "phone": phone, "role": Role.CITIZEN, "email_verified": True})
            if created:
                user.set_password(opts["password"])
                user.save()
            CitizenProfile.objects.get_or_create(user=user, defaults={"address": "Bengaluru (demo)"})
        call_command("import_dataset", "datasets/complaints_synthetic_v2.csv", "--source", "SYNTHETIC", "--dataset-version", "synthetic_v2", stdout=out)
        if not (opts["skip_training"] and MLModel.objects.filter(is_active=True).exists()):
            call_command("train_complaint_model", "--activate", "--notes", "Demo setup", stdout=out)

        if Complaint.objects.exists():
            self.stdout.write("Complaints already exist; sample complaints were not added again.")
        else:
            self._create_complaints()
        self.stdout.write(self.style.SUCCESS("Demo ready. Accounts (all use the password you chose):"))
        for line in ("admin@routelync.test (administrator)", "officer.electricity@routelync.test / officer.water@... / officer.sanitation@... / officer.roads@...",
                     "head.electricity@routelync.test (department head)", "worker.ravi.kumar@routelync.test (field worker, Electricity)",
                     "citizen@routelync.test (citizen)"):
            self.stdout.write("  " + line)

    def _create_complaints(self):
        citizens = [User.objects.get(email=e) for _, e, _ in CITIZENS]
        for ci, ward_no, street, landmark, lat, lng, title, desc, step in SAMPLES:
            ward = Ward.objects.get(number=ward_no)
            c = submit_complaint(citizen=citizens[ci], data={
                "title": title, "description": desc, "ward": ward, "street": street, "landmark": landmark, "building": "",
                "address_text": f"{street}, {ward.area.name}", "latitude": lat, "longitude": lng}, image=demo_proof_photo())
            route_complaint(c)
            c.refresh_from_db()
            if step in ("pending", "unrouted") or c.department is None:
                continue
            officer = User.objects.filter(officer_profile__department=c.department, officer_profile__is_department_head=False).first()
            worker = User.objects.filter(worker_profile__department=c.department).first()
            assign_worker(c, worker, actor=officer, note="Demo assignment")
            if step == "assigned":
                continue
            start_work(c, actor=worker)
            if step == "in_progress":
                add_remark(c, author=worker, text="Reached the site, checking the problem now.")
                continue
            complete_work(c, actor=worker, remarks="The problem was fixed and tested on site.", photo=demo_proof_photo())
            review_resolution(c, actor=officer, approve=True)
            if step == "closed":
                confirm_resolution(c, citizen=c.citizen)
                submit_feedback(c, citizen=c.citizen, rating=5, comment="Fixed quickly, thank you.")
        self.stdout.write(f"Created {Complaint.objects.count()} sample complaints through the real routing pipeline.")
