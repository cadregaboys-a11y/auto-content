import io
import json
import threading
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request
from unittest.mock import patch

from video_pipeline.captions import write_word_captions
from video_pipeline import process_video
from video_pipeline.render import render_vertical_short
from video_pipeline import visual_analysis
from video_pipeline.process_video import validate_input
from video_pipeline.visual_analysis import (
    Clip,
    SceneAnalysis,
    VisualMoment,
    _ollama_url,
    choose_retention_clips,
    generate_storytelling_script,
)


class VideoPipelineTests(unittest.TestCase):
    def test_retention_clips_are_chronological_and_match_target_duration(self) -> None:
        clips = choose_retention_clips(
            [(2.0, 0.1), (12.0, 0.9), (22.0, 0.4)],
            video_duration=30.0,
            target_duration=9.0,
        )

        self.assertEqual(clips, sorted(clips, key=lambda clip: clip.start))
        self.assertAlmostEqual(sum(clip.end - clip.start for clip in clips), 9.0)

    # def test_retention_clips_reject_target_longer_than_source(self) -> None:
    #     with self.assertRaises(ValueError):
    #         choose_retention_clips([], video_duration=4.0, target_duration=5.0)

    def test_retention_clips_repeat_short_source_to_match_target_duration(self) -> None:
        clips = choose_retention_clips(
            [],
            video_duration=4.0,
            target_duration=10.0,
        )

        self.assertAlmostEqual(sum(clip.end - clip.start for clip in clips), 10.0)
        self.assertTrue(all(0 <= clip.start < clip.end <= 4.0 for clip in clips))
        self.assertGreater(len(clips), 1)

    def test_render_uses_narration_duration_for_repeated_clips(self) -> None:
        clips = [Clip(0.0, 4.0, 0.0), Clip(0.0, 4.0, 0.0), Clip(0.0, 2.0, 0.0)]
        with tempfile.TemporaryDirectory() as temporary:
            with patch("video_pipeline.render.subprocess.run") as run:
                render_vertical_short(
                    Path(temporary) / "source.mp4",
                    Path(temporary) / "narration.mp3",
                    Path(temporary) / "captions.ass",
                    Path(temporary) / "final.mp4",
                    clips,
                    focus_x=0.5,
                    duration=10.0,
                )

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-t") + 1], "10.000")
        self.assertIn("concat=n=3", command[command.index("-filter_complex") + 1])

    def test_retention_clips_keep_multimodal_focus_position(self) -> None:
        clips = choose_retention_clips(
            [VisualMoment(timestamp=5.0, score=0.9, focus_x=0.82)],
            video_duration=20.0,
            target_duration=4.0,
        )

        self.assertAlmostEqual(clips[0].focus_x, 0.82)

    def test_story_prompt_uses_scene_and_requests_a_hook(self) -> None:
        scene = SceneAnalysis(
            summary="Un artigiano modella una tazza al tornio.",
            actions=("Le mani levigano l'argilla bagnata.",),
            moments=(VisualMoment(3.0, 0.9, 0.6),),
        )
        with patch(
            "video_pipeline.visual_analysis._call_ollama",
            return_value={"narration": "Guarda come nasce questa tazza."},
        ) as ollama:
            narration = generate_storytelling_script(
                "Un lavoro soddisfacente",
                scene,
                "La trascrizione originale",
                target_duration=12.0,
                language="it",
            )

        prompt = ollama.call_args.args[0]
        self.assertEqual(narration, "Guarda come nasce questa tazza.")
        self.assertIn("gancio forte", prompt)
        self.assertIn(scene.summary, prompt)
        self.assertIn(scene.actions[0], prompt)

    def test_long_story_retries_short_output_and_targets_75_to_115_words(self) -> None:
        scene = SceneAnalysis(
            summary="Una pressa idraulica schiaccia oggetti.",
            actions=("La pressa comprime una serie di oggetti.",),
            moments=(VisualMoment(3.0, 0.9, 0.5),),
        )
        narration = " ".join(f"parola{index}" for index in range(90))
        with patch(
            "video_pipeline.visual_analysis._call_ollama",
            side_effect=[
                {"narration": "Testo troppo breve."},
                {"narration": narration},
            ],
        ) as ollama:
            result = generate_storytelling_script(
                "Un esperimento soddisfacente",
                scene,
                "",
                target_duration=35.0,
                language="it",
            )

        self.assertEqual(result, narration)
        self.assertEqual(ollama.call_count, 2)
        self.assertIn("75-115 parole", ollama.call_args_list[1].args[0])

    def test_pipeline_retries_for_target_audio_and_repeats_short_source(self) -> None:
        script = " ".join(f"parola{index}" for index in range(90))
        scene = SceneAnalysis(
            summary="La pressa schiaccia oggetti.",
            actions=("La pressa scende e comprime.",),
            moments=(VisualMoment(4.0, 0.9, 0.5),),
        )

        with tempfile.TemporaryDirectory() as temporary:
            project_root = Path(temporary)
            output_root = project_root / "downloads" / "processed"
            output_root.mkdir(parents=True)
            with (
                patch.dict(
                    "os.environ",
                    {
                        "ELEVENLABS_API_KEY": "test-key",
                        "ELEVENLABS_VOICE_ID": "test-voice",
                    },
                ),
                patch.object(process_video, "PROJECT_ROOT", project_root),
                patch.object(process_video, "OUTPUT_ROOT", output_root),
                patch.object(
                    process_video,
                    "validate_input",
                    return_value=project_root / "source.mp4",
                ),
                patch.object(process_video, "analyze_video", return_value=(8.0, [], 0.5)),
                patch.object(process_video, "analyze_keyframes", return_value=scene),
                patch.object(process_video, "load_whisper_model", return_value=object()),
                patch.object(
                    process_video,
                    "transcribe",
                    side_effect=[{"segments": []}, {"segments": []}],
                ),
                patch.object(
                    process_video,
                    "generate_storytelling_script",
                    side_effect=[script, script],
                ) as generate_script,
                patch.object(process_video, "synthesize_narration") as synthesize,
                patch.object(process_video, "audio_duration", side_effect=[4.0, 35.0]),
                patch.object(process_video, "write_word_captions", return_value=90),
                patch.object(process_video, "render_vertical_short") as render,
                redirect_stdout(io.StringIO()),
            ):
                result = process_video.run_pipeline(
                    project_root / "source.mp4",
                    "video123",
                    "Un breve spunto",
                    "it",
                    rights_confirmed=True,
                )

        self.assertEqual(result["duration_seconds"], 35.0)
        self.assertEqual(generate_script.call_args_list[0].args[3], 35.0)
        self.assertEqual(generate_script.call_args_list[1].args[3], 40.0)
        self.assertEqual(synthesize.call_count, 2)
        rendered_clips = render.call_args.args[4]
        self.assertAlmostEqual(
            sum(clip.end - clip.start for clip in rendered_clips),
            35.0,
        )
        self.assertTrue(all(clip.end <= 8.0 for clip in rendered_clips))

    def test_ollama_endpoint_must_be_local(self) -> None:
        with patch.dict("os.environ", {"OLLAMA_HOST": "http://example.com:11434"}):
            with self.assertRaisesRegex(RuntimeError, "localhost"):
                _ollama_url()

    def test_ollama_hard_timeout_emits_json_progress(self) -> None:
        request_started = threading.Event()
        release_request = threading.Event()
        output = io.StringIO()

        def delayed_urlopen(request: Request, timeout: float) -> io.BytesIO:
            self.assertEqual(
                request.full_url,
                "http://127.0.0.1:11434/api/generate",
            )
            self.assertGreater(timeout, 0)
            request_started.set()
            release_request.wait(timeout=1)
            return io.BytesIO(b"{}")

        with (
            patch.object(visual_analysis, "OLLAMA_REQUEST_TIMEOUT_SECONDS", 0.05),
            patch.object(visual_analysis, "OLLAMA_PROGRESS_INTERVAL_SECONDS", 0.01),
            patch.object(visual_analysis, "urlopen", side_effect=delayed_urlopen),
            redirect_stdout(output),
        ):
            try:
                with self.assertRaises(TimeoutError):
                    visual_analysis._request_ollama(
                        Request("http://127.0.0.1:11434/api/generate"),
                        "qwen2.5vl:3b",
                    )
            finally:
                release_request.set()

        self.assertTrue(request_started.wait(timeout=1))
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertTrue(events)
        self.assertTrue(all(event["type"] == "progress" for event in events))
        self.assertTrue(all(event["stage"] == "frame_analysis" for event in events))

    def test_ollama_http_error_includes_status(self) -> None:
        error = HTTPError(
            "http://127.0.0.1:11434/api/generate",
            404,
            "model not found",
            hdrs=None,
            fp=io.BytesIO(b""),
        )
        with patch.object(visual_analysis, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
                visual_analysis._request_ollama(
                    Request("http://127.0.0.1:11434/api/generate"),
                    "qwen2.5vl:3b",
                )

    def test_input_must_be_inside_downloads_and_rights_must_be_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            downloads = Path(temporary) / "downloads"
            downloads.mkdir()
            video = downloads / "video_123.mp4"
            video.touch()
            original_download_root = process_video.DOWNLOAD_ROOT
            process_video.DOWNLOAD_ROOT = downloads.resolve()
            try:
                self.assertEqual(
                    validate_input(video, "video_123", rights_confirmed=True),
                    video.resolve(),
                )
                with self.assertRaises(ValueError):
                    validate_input(video, "video_123", rights_confirmed=False)
                with self.assertRaises(ValueError):
                    validate_input(video, "other_123", rights_confirmed=True)
            finally:
                process_video.DOWNLOAD_ROOT = original_download_root

    def test_word_captions_include_word_timestamps_and_highlight(self) -> None:
        transcription = {
            "segments": [
                {
                    "words": [
                        {"word": "Ciao", "start": 0.0, "end": 0.4},
                        {"word": "mondo", "start": 0.4, "end": 0.9},
                    ]
                }
            ]
        }
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "captions.ass"
            count = write_word_captions(transcription, destination)
            contents = destination.read_text(encoding="utf-8")

        self.assertEqual(count, 2)
        self.assertIn("0:00:00.00,0:00:00.40", contents)
        self.assertIn(r"{\c&H0000FFFF&\b1}", contents)


if __name__ == "__main__":
    unittest.main()
