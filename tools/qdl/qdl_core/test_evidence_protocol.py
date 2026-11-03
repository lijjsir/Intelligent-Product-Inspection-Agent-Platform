import unittest

from evidence_protocol import (
    evidence_prompt,
    format_evidence_answer,
    parse_evidence_output,
)


class EvidenceProtocolTests(unittest.TestCase):
    def test_yes_and_no_single_line(self):
        yes = format_evidence_answer("A scratch is visible.", "Yes")
        no = format_evidence_answer("No visible abnormality is observed.", "No")
        self.assertEqual(parse_evidence_output(yes)["has_defect"], "Yes")
        self.assertEqual(parse_evidence_output(no)["has_defect"], "No")

    def test_multiline_evidence_and_surrounding_fence(self):
        parsed = parse_evidence_output(
            "```text\n<evidence>\nLinear marks are visible.\nThey cross the upper surface."
            "\n</evidence>\nYes\n```"
        )
        self.assertEqual(parsed["has_defect"], "Yes")
        self.assertIn("They cross", parsed["evidence_text"])

    def test_missing_evidence_or_decision_fails(self):
        self.assertIsNone(parse_evidence_output("Scratch visible.\nYes"))
        self.assertIsNone(parse_evidence_output("<evidence>Scratch visible.</evidence>"))
        self.assertIsNone(parse_evidence_output("<evidence> </evidence>\nNo"))

    def test_prompt_excludes_json_bbox_and_confidence(self):
        prompt = evidence_prompt("bottle")
        self.assertIn("<evidence>", prompt)
        self.assertIn("Yes or No", prompt)
        self.assertNotIn("return JSON", prompt)


if __name__ == "__main__":
    unittest.main()
