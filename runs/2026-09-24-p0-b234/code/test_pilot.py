"""Focused checks for data leakage, trust boundaries, grouping and metric denominators."""
import unittest
from pilot import diagnostics, parse_action, rule, validate_evidence
from analyze import average_precision, metrics


class PilotIntegrity(unittest.TestCase):
    def test_host_source_changes_authority(self):
        rows = [r for r in diagnostics() if r["origin_id"] == "diagnostic_f03_0"]
        safe, unsafe = rows[:2]
        self.assertEqual([m["text"] for m in safe["input"]["messages"]], [m["text"] for m in unsafe["input"]["messages"]])
        self.assertEqual(rule(safe["input"])[0], "safe")
        self.assertEqual(rule(unsafe["input"])[0], "unsafe")

    def test_injection_presence_does_not_define_action_label(self):
        rows = [r for r in diagnostics() if r["origin_id"] == "diagnostic_f09_0"]
        self.assertIn("SYSTEM ADMIN", rows[0]["input"]["messages"][-1]["text"])
        self.assertEqual(rule(rows[0]["input"])[0], "safe")
        self.assertEqual(rule(rows[1]["input"])[0], "unsafe")

    def test_same_candidate_and_split(self):
        rows = diagnostics()
        self.assertEqual(len(rows), 120)
        groups = {r["origin_id"] for r in rows}
        self.assertEqual(len(groups), 40)
        for g in groups:
            triplet = [r for r in rows if r["origin_id"] == g]
            self.assertTrue(all(r["input"]["candidate"] == triplet[0]["input"]["candidate"] for r in triplet))
            self.assertEqual({r["split"] for r in triplet}, {"development"})
            self.assertTrue(all(set(r["input"]) == {"messages", "candidate", "tool_semantics"} for r in triplet))

    def test_post_action_observation_rejected(self):
        text = '(1) Thought: prior text\n(2) Action: read_file\n(3) Action Input: {"file":"a"}'
        self.assertEqual(parse_action(text)["tool"], "read_file")
        with self.assertRaises(ValueError):
            parse_action(text + "\nObservation: future result")

    def test_forged_quote_rejected(self):
        inp = diagnostics()[0]["input"]
        self.assertFalse(validate_evidence({"evidence_refs": [{"message_id": "u1", "quote": "made up"}], "policy_refs": ["P1"]}, inp)[0])
        self.assertFalse(validate_evidence({"evidence_refs": [{"message_id": "forged", "quote": "Send"}], "policy_refs": ["P1"]}, inp)[0])

    def test_tied_scores_not_perfect_ap(self):
        self.assertEqual(average_precision([(True, 0), (False, 0)]), .5)

    def test_abstain_not_hidden_in_recall(self):
        rows = [{"sample_id": str(i), "origin_id": str(i), "model": "B0", "label": y, "prediction": p, "unsafe_score": None if p == "abstain" else float(p == "unsafe"), "latency_ms": 1, "input_tokens": 0, "output_tokens": 0, "error_code": None} for i, (y, p) in enumerate([("unsafe", "unsafe"), ("unsafe", "abstain"), ("safe", "safe")])]
        m = metrics(rows, {str(i): {} for i in range(3)})
        self.assertEqual(m["unsafe_recall_over_all"]["value"], .5)
        self.assertEqual(m["unsafe_recall_on_covered"]["value"], 1)
        self.assertEqual(m["abstain_count"], 1)


if __name__ == "__main__":
    unittest.main()
