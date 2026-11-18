from complaints.models import Complaint, ComplaintStatus as S, ComplaintStatusHistory
from complaints.services.transitions import ALLOWED_TRANSITIONS, InvalidTransition, transition_complaint

from .helpers import ComplaintTestCase


class TransitionTests(ComplaintTestCase):
    def setUp(self):
        super().setUp()
        self.complaint = Complaint.objects.create(citizen=self.citizen, title="A title", description="x" * 30)

    def history(self):
        return list(ComplaintStatusHistory.objects.filter(complaint=self.complaint).values_list("from_status", "to_status"))

    def test_every_status_has_an_entry_and_only_known_targets(self):
        self.assertEqual(set(ALLOWED_TRANSITIONS), set(S))
        for targets in ALLOWED_TRANSITIONS.values():
            self.assertTrue(targets <= set(S))

    def test_resolved_is_refused_without_a_photo_of_the_completed_work(self):
        Complaint.objects.filter(pk=self.complaint.pk).update(status=S.IN_PROGRESS)
        self.complaint.refresh_from_db()
        with self.assertRaisesMessage(InvalidTransition if False else Exception, "photo of the completed work is required"):
            transition_complaint(self.complaint, S.RESOLVED, actor=self.citizen)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.IN_PROGRESS)
        self.assertEqual(self.history(), [])
        transition_complaint(self.complaint, S.RESOLVED, updates={"resolution_photo": "complaints/proof.png"})      # a photo in the same step is fine
        self.assertEqual(self.complaint.status, S.RESOLVED)

    def test_full_happy_path_is_allowed_and_recorded(self):
        Complaint.objects.filter(pk=self.complaint.pk).update(resolution_photo="complaints/proof.png")
        self.complaint.refresh_from_db()
        path = [S.AI_PROCESSING, S.DEPARTMENT_ASSIGNED, S.PENDING, S.ASSIGNED_TO_WORKER, S.IN_PROGRESS, S.RESOLVED, S.CLOSED]
        for status in path:
            transition_complaint(self.complaint, status, actor=self.citizen, note=f"to {status}")
        self.assertEqual(self.complaint.status, S.CLOSED)
        self.assertEqual(self.history(), [("SUBMITTED", "AI_PROCESSING"), ("AI_PROCESSING", "DEPARTMENT_ASSIGNED"),
                                          ("DEPARTMENT_ASSIGNED", "PENDING"), ("PENDING", "ASSIGNED_TO_WORKER"),
                                          ("ASSIGNED_TO_WORKER", "IN_PROGRESS"), ("IN_PROGRESS", "RESOLVED"),
                                          ("RESOLVED", "CLOSED")])

    def test_invalid_transition_is_refused_and_changes_nothing(self):
        with self.assertRaises(InvalidTransition):
            transition_complaint(self.complaint, S.RESOLVED)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, S.SUBMITTED)
        self.assertEqual(self.history(), [])

    def test_terminal_states_cannot_be_left(self):
        for terminal in (S.CLOSED, S.REJECTED):
            Complaint.objects.filter(pk=self.complaint.pk).update(status=terminal)
            for target in S:
                with self.assertRaises(InvalidTransition, msg=f"{terminal} -> {target}"):
                    transition_complaint(self.complaint, target)

    def test_reopen_only_from_resolved(self):
        Complaint.objects.filter(pk=self.complaint.pk).update(status=S.RESOLVED)
        transition_complaint(self.complaint, S.REOPENED)
        self.assertEqual(self.complaint.status, S.REOPENED)
        Complaint.objects.filter(pk=self.complaint.pk).update(status=S.IN_PROGRESS)
        with self.assertRaises(InvalidTransition):
            transition_complaint(self.complaint, S.REOPENED)

    def test_stale_object_cannot_bypass_the_rules(self):
        stale = Complaint.objects.get(pk=self.complaint.pk)
        transition_complaint(self.complaint, S.AI_PROCESSING)
        with self.assertRaises(InvalidTransition):             # stale copy still says SUBMITTED
            transition_complaint(stale, S.AI_PROCESSING)

    def test_extra_fields_saved_in_same_step_and_caller_object_synced(self):
        transition_complaint(self.complaint, S.AI_PROCESSING, updates={"priority_reason": "because"})
        fresh = Complaint.objects.get(pk=self.complaint.pk)
        self.assertEqual((fresh.status, fresh.priority_reason), (S.AI_PROCESSING, "because"))
        self.assertEqual((self.complaint.status, self.complaint.priority_reason), (S.AI_PROCESSING, "because"))

    def test_actor_and_note_recorded(self):
        transition_complaint(self.complaint, S.AI_PROCESSING, actor=self.citizen, note="started")
        entry = ComplaintStatusHistory.objects.get()
        self.assertEqual((entry.changed_by, entry.note), (self.citizen, "started"))
