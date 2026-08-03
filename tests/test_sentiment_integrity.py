import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from sentiment_integrity import summarize_sentiment  # noqa: E402
from weekly_release_common import _combined_metric, _platform_metric  # noqa: E402


def record(label=None, *, model="domain", status="ok", confidence=0.8):
    row = {
        "sentiment_label": label,
        "sentiment_model": model,
        "sentiment_model_version": "1",
        "sentiment_status": status,
        "sentiment_score": confidence,
        "bvid": "BV1",
    }
    if label:
        row["sentiment_probabilities"] = {
            "positive": confidence if label == "positive" else (1 - confidence) / 2,
            "neutral": confidence if label == "neutral" else (1 - confidence) / 2,
            "negative": confidence if label == "negative" else (1 - confidence) / 2,
        }
    return row


class SentimentIntegrityTests(unittest.TestCase):
    def test_no_valid_evidence_is_null_not_zero(self):
        summary = summarize_sentiment([record(None, model="")])
        self.assertEqual(summary["sentiment_valid_count"], 0)
        self.assertIsNone(summary["negative_rate"])
        self.assertEqual(summary["sentiment_status"], "sentiment_data_unavailable")

    def test_true_zero_preserves_counts_and_low_sample(self):
        summary = summarize_sentiment([record("neutral") for _ in range(4)])
        self.assertEqual(summary["negative_count"], 0)
        self.assertEqual(summary["sentiment_valid_count"], 4)
        self.assertEqual(summary["negative_rate"], 0.0)
        self.assertTrue(summary["low_sample_status"])

    def test_chinese_label_mapping_and_count_identity(self):
        rows = [record("neutral"), record("negative")]
        rows[0]["sentiment_label"] = " 中性 "
        rows[1]["sentiment_label"] = "负面"
        summary = summarize_sentiment(rows)
        self.assertEqual(
            summary["positive_count"] + summary["neutral_count"] + summary["negative_count"],
            summary["sentiment_valid_count"],
        )
        self.assertEqual(summary["negative_rate"], 50.0)

    def test_low_sample_sentiment_does_not_contribute_to_risk(self):
        metric = _platform_metric(
            [record("neutral") for _ in range(4)], None, platform="B站", simulated=False
        )
        self.assertEqual(metric["risk_status"], "sentiment_low_sample")
        self.assertEqual(metric["risk_components"]["sentiment"], 0.0)
        self.assertEqual(metric["risk_components"]["disagreement"], 0.0)

    def test_combined_rate_uses_valid_counts_not_comment_counts(self):
        bili = _platform_metric(
            [record("negative")] * 2, None, platform="B站", simulated=False
        )
        hey = _platform_metric(
            [record("positive")] * 8, None, platform="小黑盒", simulated=False
        )
        combined = _combined_metric(bili, hey, simulated=False)
        self.assertEqual(combined["negative_count"], 2)
        self.assertEqual(combined["sentiment_valid_count"], 10)
        self.assertEqual(combined["negative_rate"], 20.0)

    def test_frontend_has_no_missing_to_zero_sentiment_fallback(self):
        for path in (ROOT / "index.html", ROOT / "game_sentiment_dashboard_v5.html"):
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("m?.negative_rate", source)
                self.assertIn("情感数据不足", source)
                self.assertIn("sentiment_valid_count", source)
                self.assertNotIn("Number(m?.negative)", source)
                self.assertNotIn("reviewedNegativeRate", source)
                self.assertNotIn("negative:weightedRealMetric", source)


if __name__ == "__main__":
    unittest.main()
