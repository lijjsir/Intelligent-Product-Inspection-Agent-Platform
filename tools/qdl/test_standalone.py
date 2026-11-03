import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from qdl_http import OpenAIClient
from predict import _load_model, evaluate
from run_qdl import main


class Response:
    def __init__(self, finish_reason="stop"):
        self.body = {"choices": [{"message": {"content": "<evidence>red apple</evidence>\nNo"},
                                  "finish_reason": finish_reason}]}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return json.dumps(self.body).encode()


class StandaloneTests(unittest.TestCase):
    def test_image_is_a_multimodal_block_and_output_budget_is_forwarded(self):
        client = OpenAIClient()
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "sample.png"
            image.write_bytes(b"test image bytes")
            with patch.object(client.opener, "open", return_value=Response()) as opened:
                client.generate(image, "inspect", 256)
            request = opened.call_args.args[0]
            self.assertTrue(request.full_url.endswith("/v1/chat/completions"))
            data = json.loads(request.data)
            self.assertEqual(data["max_tokens"], 256)
            self.assertEqual(data["reasoning_effort"], "none")
            self.assertTrue(data["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_truncated_outputs_are_not_accepted_as_complete_evidence(self):
        client = OpenAIClient()
        with patch.object(client.opener, "open", return_value=Response("length")):
            with self.assertRaisesRegex(RuntimeError, "truncated"):
                client.chat("test")

    def test_api_backend_does_not_load_torch_or_an_adapter(self):
        model, processor = _load_model(None, None, "float16", backend="openai")
        self.assertIsInstance(model, OpenAIClient)
        self.assertIsNone(processor)
        with self.assertRaisesRegex(ValueError, "LoRA"):
            _load_model(None, "adapter", "float16", backend="openai")

    def test_matching_preserves_split_and_reports_bad_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            row = {"id": "sample", "split": "test", "text_structured": {"has_defect": "Yes"},
                   "image_structured": {"has_defect": "No"}}
            source = root / "in.jsonl"
            target = root / "out.jsonl"
            source.write_text(json.dumps(row) + '\n{"image_structured":{}}\n', encoding="utf-8")
            self.assertEqual(main(["--input", str(source), "--output", str(target)]), 1)
            records = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(records[0]["split"], "test")
            self.assertFalse(records[0]["qdl_result"]["audit"]["llm_review_used"])
            self.assertEqual(records[1]["status"], "error")

    def test_unlabeled_image_does_not_report_zero_accuracy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "sample.png"
            image.write_bytes(b"test")
            with patch("predict._generate", return_value="<evidence>visible object</evidence>\nNo"):
                result = evaluate([{"image": str(image)}], None, None, 64,
                                  root / "out.jsonl", prompt_mode="evidence-first")
            self.assertIsNone(result["has_defect_accuracy"])
            self.assertEqual(result["labeled_samples"], 0)


if __name__ == "__main__":
    unittest.main()
