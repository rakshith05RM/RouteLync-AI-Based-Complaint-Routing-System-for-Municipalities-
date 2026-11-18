from django.test import SimpleTestCase, override_settings

from ml_engine.evaluate import auto_route_stats, choose_threshold, classification_metrics


class EvaluateTests(SimpleTestCase):
    def test_metrics_on_known_example(self):
        y_true = ["A", "A", "A", "B", "B", "B"]
        y_pred = ["A", "A", "B", "B", "B", "B"]
        m = classification_metrics(y_true, y_pred, ["A", "B"])
        self.assertAlmostEqual(m["accuracy"], 5 / 6)
        self.assertAlmostEqual(m["per_class"]["A"]["precision"], 1.0)
        self.assertAlmostEqual(m["per_class"]["A"]["recall"], 2 / 3)
        self.assertAlmostEqual(m["per_class"]["B"]["precision"], 3 / 4)
        self.assertEqual(m["confusion_matrix"], [[2, 1], [0, 3]])
        self.assertEqual(m["per_class"]["B"]["support"], 3)

    def test_auto_route_stats(self):
        stats = auto_route_stats([0.9, 0.8, 0.4, 0.3], [True, False, False, True], 0.5)
        self.assertEqual(stats["auto_routed_share"], 0.5)
        self.assertEqual(stats["auto_routed_accuracy"], 0.5)
        self.assertIsNone(auto_route_stats([0.2], [True], 0.9)["auto_routed_accuracy"])

    @override_settings(ML_TARGET_PRECISION=0.95, ML_MIN_THRESHOLD=0.5)
    def test_threshold_selection(self):
        conf = [0.99, 0.95, 0.9, 0.6, 0.55]
        # wrong predictions only at low confidence -> a threshold above 0.6 is enough
        t, met = choose_threshold(conf, [True, True, True, False, False])
        self.assertTrue(met)
        self.assertGreater(t, 0.6)
        # the floor is respected even when everything is correct
        t, met = choose_threshold(conf, [True] * 5)
        self.assertEqual((t, met), (0.5, True))
        # target unreachable -> conservative fallback
        t, met = choose_threshold(conf, [False] * 5)
        self.assertEqual((t, met), (0.9, False))
