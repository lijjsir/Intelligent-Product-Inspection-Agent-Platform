import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from predict import OllamaAPIClient, _load_model


class OllamaBackendTests(unittest.TestCase):
    def test_posts_image_and_prompt_to_chat_api(self):
        with tempfile.TemporaryDirectory() as directory:
            image_path = Path(directory) / "sample.png"
            image_path.write_bytes(b"fake-image")

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

                def read(self):
                    return b'{"message":{"content":"<evidence>scratch</evidence>\\nYes"}}'

            with patch("urllib.request.urlopen", return_value=Response()) as urlopen:
                result = OllamaAPIClient("http://127.0.0.1:11434", "vision:test").generate(
                    str(image_path), "inspect this", 64,
                )

            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
            body = json.loads(request.data)
            self.assertEqual(body["model"], "vision:test")
            self.assertEqual(body["messages"][0]["content"], "inspect this")
            self.assertEqual(
                base64.b64decode(body["messages"][0]["images"][0]), b"fake-image",
            )
            self.assertEqual(result, "<evidence>scratch</evidence>\nYes")

    def test_ollama_does_not_require_transformers_model_path(self):
        client, processor = _load_model(
            None, None, "float16", backend="ollama", ollama_model="vision:test",
        )
        self.assertIsInstance(client, OllamaAPIClient)
        self.assertIsNone(processor)


if __name__ == "__main__":
    unittest.main()
