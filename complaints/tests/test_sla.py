from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from complaints.sla import sla_state
from departments.models import Priority, SLAConfiguration
from departments.services import DEFAULT_SLA_HOURS, sla_hours_for


class SlaStateTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_time_remaining(self):
        s = sla_state(self.now + timedelta(hours=3, minutes=20), self.now)
        self.assertFalse(s.is_overdue)
        self.assertEqual(s.label, "3 h 20 min remaining")

    def test_overdue(self):
        s = sla_state(self.now - timedelta(hours=3, minutes=5), self.now)
        self.assertTrue(s.is_overdue)
        self.assertEqual(s.label, "Overdue by 3 h 5 min")
        self.assertLess(s.seconds, 0)

    def test_long_and_short_spans(self):
        self.assertEqual(sla_state(self.now + timedelta(days=2, hours=4), self.now).label, "2 d 4 h remaining")
        self.assertEqual(sla_state(self.now + timedelta(minutes=45), self.now).label, "45 min remaining")
        self.assertEqual(sla_state(self.now - timedelta(days=1, hours=2), self.now).label, "Overdue by 1 d 2 h")

    def test_exactly_at_deadline_is_not_overdue(self):
        self.assertFalse(sla_state(self.now, self.now).is_overdue)

    def test_no_deadline(self):
        self.assertEqual(sla_state(None).label, "No deadline set")


class SlaHoursTests(TestCase):
    def test_defaults_are_examples_and_configured_values_win(self):
        self.assertEqual({p: sla_hours_for(p) for p in Priority.values}, {str(k): v for k, v in DEFAULT_SLA_HOURS.items()})
        SLAConfiguration.objects.create(priority=Priority.CRITICAL, hours=2)
        self.assertEqual(sla_hours_for(Priority.CRITICAL), 2)
        self.assertEqual(sla_hours_for(Priority.LOW), 72)
