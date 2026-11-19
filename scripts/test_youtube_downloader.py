import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import youtube_downloader
from youtube_downloader import (
    _candidate_is_eligible,
    _candidate_priority,
    has_allowed_license,
)


class AllowedLicenseTests(unittest.TestCase):
    def test_accepts_youtube_creative_commons_attribution_license(self) -> None:
        self.assertTrue(
            has_allowed_license("Creative Commons Attribution license (reuse allowed)")
        )

    def test_rejects_missing_or_unrecognized_license(self) -> None:
        self.assertFalse(has_allowed_license(None))
        self.assertFalse(has_allowed_license("Standard YouTube License"))
        self.assertFalse(has_allowed_license("Creative Commons Attribution"))

    def test_candidate_filters_duration_shorts_and_portrait_orientation(self) -> None:
        base = {
            "webpage_url": "https://youtube.com/watch?v=video12345",
            "duration": 300,
            "width": 1280,
            "height": 720,
        }
        self.assertTrue(_candidate_is_eligible(base))
        self.assertTrue(
            _candidate_is_eligible(
                {**base, "duration": 60, "height": None, "width": None}
            )
        )
        self.assertTrue(
            _candidate_is_eligible(
                {**base, "duration": 900, "height": None, "width": None}
            )
        )
        self.assertFalse(_candidate_is_eligible({**base, "duration": 59}))
        self.assertFalse(_candidate_is_eligible({**base, "duration": 901}))
        self.assertFalse(
            _candidate_is_eligible(
                {**base, "webpage_url": "https://youtube.com/shorts/video12345"}
            )
        )
        self.assertFalse(_candidate_is_eligible({**base, "width": 720, "height": 1280}))

    def test_candidate_priority_prefers_horizontal_ideal_duration(self) -> None:
        ideal_landscape = {
            "duration": 450,
            "width": 1920,
            "height": 1080,
        }
        landscape_outside_ideal = {
            "duration": 720,
            "width": 1920,
            "height": 1080,
        }
        ideal_unknown_orientation = {"duration": 450}

        self.assertGreater(
            _candidate_priority(ideal_landscape),
            _candidate_priority(landscape_outside_ideal),
        )
        self.assertGreater(
            _candidate_priority(ideal_landscape),
            _candidate_priority(ideal_unknown_orientation),
        )

    def test_search_verifies_full_metadata_and_reports_download_progress(self) -> None:
        class FakeYouTubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return not exc_info

            def extract_info(self, url, download=False):
                if url.startswith("ytsearch"):
                    return {
                        "entries": [
                            {"webpage_url": "https://youtube.com/watch?v=bad12345"},
                            {"webpage_url": "https://youtube.com/watch?v=abc12345"},
                        ]
                    }
                if not download:
                    return {
                        "id": url.rsplit("=", 1)[-1],
                        "title": "Ceramica al tornio",
                        "webpage_url": url,
                        "license": (
                            "Standard YouTube License"
                            if "bad12345" in url
                            else "Creative Commons Attribution license (reuse allowed)"
                        ),
                        "duration": 420,
                        "width": 1280,
                        "height": 720,
                    }

                for hook in self.options.get("progress_hooks", []):
                    hook({"status": "downloading", "downloaded_bytes": 50, "total_bytes": 100})
                    hook({"status": "finished"})
                return {
                    "id": "abc12345",
                    "title": "Ceramica al tornio",
                    "webpage_url": url,
                    "license": "Creative Commons Attribution license (reuse allowed)",
                    "filepath": "abc12345.mp4",
                }

        with tempfile.TemporaryDirectory() as temporary:
            events = []
            with (
                patch.object(youtube_downloader, "DOWNLOAD_DIR", Path(temporary)),
                patch.object(youtube_downloader.yt_dlp, "YoutubeDL", FakeYouTubeDL),
            ):
                videos = youtube_downloader.download_matches(
                    "ceramica artigianale",
                    1,
                    events.append,
                )

        self.assertEqual(len(videos), 1)
        self.assertEqual(videos[0]["id"], "abc12345")
        self.assertEqual(videos[0]["license"], "Creative Commons Attribution license (reuse allowed)")
        self.assertTrue(any(event["stage"] == "search" for event in events))
        self.assertTrue(any(event["stage"] == "download" for event in events))
        self.assertTrue(any(event["stage"] == "download" and event["stage_progress"] == 100 for event in events))

    def test_search_filters_before_download_and_sorts_ideal_landscape_first(self) -> None:
        metadata_by_id = {
            "long12345": {
                "duration": 720,
                "width": 1920,
                "height": 1080,
            },
            "short12345": {
                "duration": 45,
                "width": 1920,
                "height": 1080,
            },
            "vertical1": {
                "duration": 420,
                "width": 720,
                "height": 1280,
            },
            "toolong12": {
                "duration": 901,
                "width": 1920,
                "height": 1080,
            },
            "ideal12345": {
                "duration": 420,
                "width": 1280,
                "height": 720,
            },
        }
        downloaded_ids = []

        class FakeYouTubeDL:
            def __init__(self, options):
                self.options = options

            def __enter__(self):
                return self

            def __exit__(self, *exc_info):
                return not exc_info

            def extract_info(self, url, download=False):
                if url.startswith("ytsearch"):
                    return {
                        "entries": [
                            {"webpage_url": f"https://youtube.com/watch?v={video_id}"}
                            for video_id in metadata_by_id
                        ]
                        + [
                            {
                                "webpage_url": "https://youtube.com/shorts/short12345"
                            }
                        ]
                    }

                video_id = url.rsplit("=", 1)[-1]
                metadata = metadata_by_id[video_id]
                result = {
                    **metadata,
                    "id": video_id,
                    "title": video_id,
                    "webpage_url": url,
                    "license": "Creative Commons Attribution license (reuse allowed)",
                }
                if download:
                    match_filter = self.options["match_filter"]
                    self.assert_candidate_allowed(match_filter, result)
                    downloaded_ids.append(video_id)
                    result["filepath"] = f"{video_id}.mp4"
                return result

            @staticmethod
            def assert_candidate_allowed(match_filter, result):
                if match_filter(result, incomplete=False):
                    raise AssertionError("A filtered candidate reached the download stage.")

        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.object(youtube_downloader, "DOWNLOAD_DIR", Path(temporary)),
                patch.object(youtube_downloader.yt_dlp, "YoutubeDL", FakeYouTubeDL),
            ):
                videos = youtube_downloader.download_matches(
                    "pressa idraulica",
                    1,
                )

        self.assertEqual(downloaded_ids, ["ideal12345"])
        self.assertEqual([video["id"] for video in videos], ["ideal12345"])


if __name__ == "__main__":
    unittest.main()
