import json
import os
import subprocess
from pathlib import Path

from .visual_analysis import Clip


def audio_duration(audio_path: Path) -> float:
    probe = subprocess.run(
        [
            os.environ.get("FFPROBE_EXECUTABLE", "ffprobe"),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    if duration <= 0:
        raise RuntimeError("La durata dell'audio narrato non è valida.")
    return duration


def render_vertical_short(
    video_path: Path,
    narration_path: Path,
    captions_path: Path,
    output_path: Path,
    clips: list[Clip],
    focus_x: float,
    duration: float,
) -> None:
    if not clips:
        raise ValueError("Nessun segmento video da montare.")

    filters: list[str] = []
    labels = "".join(f"[source{index}]" for index in range(len(clips)))
    if len(clips) > 1:
        filters.append(f"[0:v]split={len(clips)}{labels}")

    for index, clip in enumerate(clips):
        source = f"[source{index}]" if len(clips) > 1 else "[0:v]"
        clip_focus = max(0.0, min(1.0, clip.focus_x))
        filters.append(
            f"{source}trim=start={clip.start:.3f}:duration={clip.end - clip.start:.3f},"
            "setpts=PTS-STARTPTS,"
            "crop=w='min(iw,ih*9/16)':h=ih:"
            f"x='max(0,min(iw-ow,iw*{clip_focus:.6f}-ow/2))':y=0,"
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1"
            f"[clip{index}]"
        )

    concatenated = "".join(f"[clip{index}]" for index in range(len(clips)))
    filters.append(
        f"{concatenated}concat=n={len(clips)}:v=1:a=0[video];"
        # "[video]subtitles=captions.ass:"
        # "force_style='FontName=Arial,FontSize=62,Alignment=2,MarginV=170'[output]"
        "[video]subtitles=captions.ass[output]"
    )
    filter_graph = ";".join(filters)

    subprocess.run(
        [
            os.environ.get("FFMPEG_EXECUTABLE", "ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(narration_path),
            "-filter_complex",
            filter_graph,
            "-map",
            "[output]",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=3600,
        cwd=output_path.parent,
    )
