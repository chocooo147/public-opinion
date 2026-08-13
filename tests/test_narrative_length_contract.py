from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_narratives import validate_driver  # noqa: E402


def _driver(narrative_en: str, narrative_zh: str) -> dict[str, object]:
    return {
        "topic_en": "Narrative Length Fixture",
        "topic_zh": "叙述长度联调主题",
        "narrative_en": narrative_en,
        "narrative_zh": narrative_zh,
    }


class NarrativeLengthContractTests(unittest.TestCase):
    def test_contract_declares_the_new_length_rule(self):
        contract = json.loads(
            (ROOT / "config" / "weekly_bilingual_report_contract.json").read_text(
                encoding="utf-8"
            )
        )
        policy = contract["narrative_policy"]
        self.assertEqual(policy["minimum_sentences_per_language"], 1)
        self.assertEqual(policy["english_narrative_word_minimum"], 20)
        self.assertEqual(policy["english_narrative_word_maximum"], 75)

    def test_validator_accepts_one_sentence_and_twenty_english_words(self):
        narrative_en = (
            "Some players discussed the updated feature, described clearer rules, and said "
            "the explanation improved understanding and informed their decisions directly."
        )
        narrative_zh = "部分玩家认为更新功能的规则说明更清楚，并讨论了实际变化如何帮助理解细节、形成后续参与判断和避免误解。"
        self.assertEqual(
            len(re.findall(r"\b[\w’'-]+\b", narrative_en)),
            20,
        )
        errors = validate_driver(_driver(narrative_en, narrative_zh), 1)
        self.assertEqual(errors, [])

    def test_validator_rejects_english_narrative_over_the_contract_maximum(self):
        narrative_en = "Players discussed details and reported improved understanding " + (
            "context " * 70
        ) + "today."
        narrative_zh = "部分玩家认为更新功能的规则说明更清楚，并讨论了实际变化如何帮助理解细节、形成后续参与判断和避免误解。"
        errors = validate_driver(_driver(narrative_en, narrative_zh), 1)
        self.assertTrue(
            any("English narrative length 78 is outside 20-75 words" in error for error in errors)
        )


if __name__ == "__main__":
    unittest.main()
