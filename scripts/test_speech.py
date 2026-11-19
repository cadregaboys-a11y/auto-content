import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from unittest.mock import patch

from video_pipeline import process_video, speech


class SpeechTests(unittest.TestCase):
    def test_synthesis_posts_configured_voice_and_writes_audio(self) -> None:
        audio = b"mock mp3 audio"
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "narration.mp3"
            with (
                patch.dict(
                    os.environ,
                    {
                        "ELEVENLABS_API_KEY": "test-api-key",
                        "ELEVENLABS_VOICE_ID": "test-voice-id",
                    },
                ),
                patch.object(speech, "urlopen", return_value=io.BytesIO(audio)) as urlopen,
            ):
                speech.synthesize_narration("Ciao mondo", destination)
                # request, timeout = urlopen.call_args.args
                request = urlopen.call_args.args[0]
                timeout = urlopen.call_args.kwargs["timeout"]
                self.assertIsInstance(request, Request)
                self.assertEqual(
                    request.full_url,
                    "https://api.elevenlabs.io/v1/text-to-speech/test-voice-id"
                    "?output_format=mp3_44100_128",
                )
                self.assertEqual(timeout, 120)
                self.assertEqual(request.get_method(), "POST")
                # self.assertEqual(request.get_header("X-api-key"), "test-api-key")
                headers = {name.lower(): value for name, value in request.headers.items()}
                self.assertEqual(headers["xi-api-key"], "test-api-key")
                self.assertEqual(headers["content-type"], "application/json")
                self.assertEqual(
                    json.loads(request.data),
                    {
                        "text": "Ciao mondo",
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.45,
                            "similarity_boost": 0.75,
                        },
                    },
                )
                self.assertEqual(destination.read_bytes(), audio)

    def test_http_error_is_complete_in_pipeline_stderr_not_stdout(self) -> None:
        api_detail = '{"detail":{"status":"invalid_voice","message":"' + ("x" * 2500) + '"}}'
        http_error = HTTPError(
            "https://api.elevenlabs.io/v1/text-to-speech/test-voice-id",
            422,
            "Unprocessable Entity",
            hdrs=None,
            fp=io.BytesIO(api_detail.encode("utf-8")),
        )
        stderr = io.StringIO()
        stdout = io.StringIO()

        def run_synthesis(*arguments: object) -> None:
            self.assertEqual(len(arguments), 5)
            speech.synthesize_narration("Ciao mondo", Path("unused.mp3"))

        with (
            patch.dict(
                os.environ,
                {
                    "ELEVENLABS_API_KEY": "test-api-key",
                    "ELEVENLABS_VOICE_ID": "test-voice-id",
                },
            ),
            patch.object(speech, "urlopen", side_effect=http_error),
            patch.object(
                process_video,
                "run_pipeline",
                side_effect=run_synthesis,
            ),
            patch.object(
                sys,
                "argv",
                [
                    "process_video.py",
                    "--input",
                    "input.mp4",
                    "--video-id",
                    "video123",
                    "--brief",
                    "Un breve spunto",
                    "--rights-confirmed",
                ],
            ),
            redirect_stderr(stderr),
            redirect_stdout(stdout),
        ):
            result = process_video.main()

        self.assertEqual(result, 1)
        self.assertIn("HTTP 422", stderr.getvalue())
        self.assertIn(api_detail, stderr.getvalue())
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
