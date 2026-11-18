"""
The complete demonstration scenario through the real web pages, with a really trained model:
citizen submits -> AI routes -> officer filters and assigns -> worker starts and completes ->
officer verifies -> citizen confirms.
"""
import io

from django.core.management import call_command
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import Complaint, ComplaintStatus as S
from ml_engine.train import train_and_evaluate

from .helpers import make_upload
from .test_routing import RoutingBase


class EndToEndTests(RoutingBase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", stdout=io.StringIO())
        call_command("import_dataset", "datasets/complaints_synthetic_v1.csv", "--source", "SYNTHETIC", stdout=io.StringIO())
        train_and_evaluate(activate=True)

    def test_whole_journey(self):
        from departments.models import Department
        elec = Department.objects.get(code="ELECTRICITY")
        officer = make_user("officer@example.com", Role.OFFICER, department=elec, full_name="Meera Nair")
        worker = make_user("ravi@example.com", Role.FIELD_WORKER, department=elec, full_name="Ravi Kumar")

        # 1-5: the citizen submits; the backend routes the complaint
        self.client.force_login(self.citizen)
        self.client.post(reverse("complaints:new"), self.payload(latitude="12.925012", longitude="77.5938", image=make_upload("pole.png")))
        c = Complaint.objects.get()
        self.assertEqual((c.status, c.department.code), (S.PENDING, "ELECTRICITY"))
        self.assertIn("Sent to Electricity", self.client.get(reverse("complaints:detail", args=[c.pk])).content.decode())

        # 6-8: the officer finds it by area, ward and street, and assigns a worker
        self.client.force_login(officer)
        listing = self.client.get(reverse("officer:dashboard"), {"area": self.area.pk, "ward": self.ward.pk, "street": "4th Main Road"})
        self.assertEqual([x.pk for x in listing.context["complaints"]], [c.pk])
        self.client.post(reverse("officer:assign", args=[c.pk]), {"worker": worker.pk})
        self.assertEqual(Complaint.objects.get().status, S.ASSIGNED_TO_WORKER)

        # 9-10: the worker starts and completes the job
        self.client.force_login(worker)
        self.assertEqual([x.pk for x in self.client.get(reverse("worker:dashboard")).context["complaints"]], [c.pk])
        self.client.post(reverse("worker:start", args=[c.pk]))
        self.client.post(reverse("worker:complete", args=[c.pk]), {"remarks": "Replaced the lamp and tested it at night.", "photo": make_upload("done.png")})
        self.assertEqual(Complaint.objects.get().status, S.IN_PROGRESS)

        # 11: the officer verifies
        self.client.force_login(officer)
        self.client.post(reverse("officer:review", args=[c.pk]), {"decision": "approve", "note": ""})
        self.assertEqual(Complaint.objects.get().status, S.RESOLVED)

        # 12-13: the citizen sees it resolved and confirms
        self.client.force_login(self.citizen)
        page = self.client.get(reverse("complaints:detail", args=[c.pk])).content.decode()
        self.assertIn("Is the problem fixed?", page)
        self.client.post(reverse("complaints:confirm", args=[c.pk]))
        final = Complaint.objects.get()
        self.assertEqual(final.status, S.CLOSED)
        timeline = [h.to_status for h in final.status_history.all()]
        for expected in ("SUBMITTED", "AI_PROCESSING", "DEPARTMENT_ASSIGNED", "PENDING", "ASSIGNED_TO_WORKER", "IN_PROGRESS", "RESOLVED", "CLOSED"):
            self.assertIn(expected, timeline)
