"""Train the real model on all seventeen departments and check it end to end, including a citizen submitting for each one."""
import csv
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.urls import reverse

from accounts.models import Role
from accounts.tests.helpers import make_user
from complaints.models import Complaint, SubmissionAttempt
from complaints.services.description_check import check_description
from complaints.tests.helpers import make_upload
from departments.models import Ward
from ml_engine.data_generation import ALL_ISSUES
from ml_engine.model_manager import get_active_model
from ml_engine.train import train_and_evaluate

from .helpers import MLTestCase


def read(name):
    with open(Path(settings.DATASETS_DIR) / name, encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class SeventeenDepartmentTests(MLTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_master_data", stdout=StringIO())
        call_command("import_dataset", str(Path(settings.DATASETS_DIR) / "complaints_synthetic_v2.csv"),
                     "--source", "SYNTHETIC", "--dataset-version", "synthetic_v2", stdout=StringIO())
        cls.result = train_and_evaluate(notes="seventeen departments", activate=True)

    def test_the_model_knows_all_seventeen_departments(self):
        row, pipeline = get_active_model()
        self.assertEqual(set(row.labels), set(ALL_ISSUES))
        self.assertEqual(len(row.labels), 17)
        self.assertGreaterEqual(row.accuracy, 0.97)
        self.assertEqual(row.dataset_size, 5097)

    def test_honest_accuracy_on_hand_written_complaints(self):
        row, _ = get_active_model()
        self.assertGreaterEqual(row.challenge_report["accuracy"], 0.80)        # measured 0.851 on 194 complaints
        out = StringIO()
        call_command("evaluate_model", str(Path(settings.DATASETS_DIR) / "challenge_set_v3.csv"), stdout=out)
        correct, total = (int(x) for x in out.getvalue().split(": ")[1].split(" correct")[0].split("/"))
        self.assertEqual(total, 51)
        self.assertGreaterEqual(correct / total, 0.90)                           # measured 48/51 on complaints written before the final training data

    def test_every_department_is_reachable(self):
        out = StringIO()
        call_command("evaluate_model", str(Path(settings.DATASETS_DIR) / "challenge_set_v3.csv"), stdout=out)
        per_department = {}
        for line in out.getvalue().splitlines():
            parts = line.split()
            if len(parts) == 2 and "/" in parts[1]:
                per_department[parts[0]] = int(parts[1].split("/")[0])
        self.assertEqual(set(per_department), set(ALL_ISSUES))
        self.assertTrue(all(v >= 1 for v in per_department.values()), per_department)

    def test_the_description_check_accepts_real_complaints_for_every_department(self):
        refused = [r["text"] for name in ("challenge_set_v2.csv", "challenge_set_v3.csv") for r in read(name)
                   if not check_description(r["text"]).accepted]
        self.assertEqual(refused, [])

    def test_the_second_opinion_rescues_unusual_wording_but_not_junk(self):
        with_model = {"valid refused": 0, "junk accepted": 0}
        for name in ("description_heldout4.csv", "description_heldout5.csv"):
            for r in read(name):
                accepted = check_description(r["text"]).accepted
                if r["expected"] == "accept" and not accepted:
                    with_model["valid refused"] += 1
                if r["expected"] == "reject" and accepted:
                    with_model["junk accepted"] += 1
        self.assertLessEqual(with_model["valid refused"], 3)         # measured 2 of 68 (fresh sets, small)
        self.assertLessEqual(with_model["junk accepted"], 1)         # measured 0 of 32
        self.assertTrue(check_description("Teachers at the municipal school arrive late and leave early every day").accepted)
        self.assertFalse(check_description("I need to renew my driving licence at the transport office").accepted)

    def test_a_citizen_can_report_a_problem_for_each_department_and_it_is_routed(self):
        ward = Ward.objects.get(number=154)
        first_per_department = {}
        for r in read("challenge_set_v3.csv"):
            first_per_department.setdefault(r["department_code"], r["text"])
        routed_right = 0
        for index, (code, text) in enumerate(first_per_department.items()):
            citizen = make_user(f"citizen{index}@example.com", Role.CITIZEN)
            self.client.force_login(citizen)
            response = self.client.post(reverse("complaints:new"), {
                "title": "Problem in our area", "description": text, "area": ward.area_id, "ward": ward.pk, "street": "4th Main Road",
                "landmark": "", "building": "", "address_text": "4th Main Road, Jayanagar", "latitude": "12.925000", "longitude": "77.593800",
                "image": make_upload(), "submission_token": f"{index:032d}"})
            self.assertEqual(response.status_code, 302, f"{code}: {text}")          # accepted, not refused by the description check
            complaint = Complaint.objects.get(citizen=citizen)
            if complaint.department and complaint.department.code == code:
                routed_right += 1
            else:                                                                   # never lost: either another department or a person decides
                self.assertIn(complaint.status, ("PENDING", "NEEDS_VERIFICATION"))
        self.assertEqual(SubmissionAttempt.objects.count(), 0)
        self.assertGreaterEqual(routed_right, 14, routed_right)                    # measured 16 of 17

    def test_a_complaint_for_a_department_outside_the_list_is_refused_clearly(self):
        citizen = make_user("outsider@example.com", Role.CITIZEN)
        self.client.force_login(citizen)
        ward = Ward.objects.get(number=154)
        response = self.client.post(reverse("complaints:new"), {
            "title": "Ration card", "description": "Please help me correct the name on my ration card as soon as possible", "area": ward.area_id,
            "ward": ward.pk, "street": "4th Main Road", "address_text": "4th Main Road, Jayanagar", "latitude": "12.925", "longitude": "77.5938",
            "image": make_upload()})
        self.assertContains(response, "outside the currently supported complaint categories")
        self.assertFalse(Complaint.objects.exists())
