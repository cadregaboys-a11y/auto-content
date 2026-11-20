import json
import os
import random
import re
import subprocess
from pathlib import Path

from .captions import CAPTION_FONT_DIRECTORY
from .events import report_progress
from .visual_analysis import Clip


MUSIC_DIRECTORY = Path(__file__).resolve().parents[2] / "assets" / "music"
AUDIO_SILENCE_THRESHOLD_DB = -55.0


def _select_background_music() -> Path | None:
    MUSIC_DIRECTORY.mkdir(parents=True, exist_ok=True)
    music_files = sorted(
        path
        for path in MUSIC_DIRECTORY.iterdir()
        if path.is_file() and path.suffix.casefold() in {".mp3", ".wav"}
    )
    return random.choice(music_files) if music_files else None


def _escape_filter_path(path: Path) -> str:
    return (
        str(path.resolve())
        .replace("\\", "/")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace(",", r"\,")
    )


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


def _measure_audio_peak(audio_path: Path) -> float:
    probe = subprocess.run(
        [
            os.environ.get("FFMPEG_EXECUTABLE", "ffmpeg"),
            "-hide_banner",
            "-i",
            str(audio_path),
            "-vn",
            "-af",
            "volumedetect",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if probe.returncode != 0:
        detail = probe.stderr.strip()[-1000:] or "errore FFmpeg non specificato"
        raise RuntimeError(
            f"Impossibile leggere il livello audio di {audio_path}: {detail}"
        )
    match = re.search(
        r"max_volume:\s*(-?(?:\d+(?:\.\d+)?|inf))\s*dB",
        probe.stderr,
        flags=re.IGNORECASE,
    )
    if match is None:
        raise RuntimeError(
            f"FFmpeg non ha restituito il livello di picco per {audio_path}."
        )
    return float(match.group(1))


def _verify_rendered_audio(output_path: Path) -> tuple[str, float]:
    probe = subprocess.run(
        [
            os.environ.get("FFPROBE_EXECUTABLE", "ffprobe"),
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "json",
            str(output_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    streams = json.loads(probe.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(
            f"Il video renderizzato non contiene una traccia audio: {output_path}"
        )
    codec = str(streams[0].get("codec_name", "sconosciuto"))
    peak_db = _measure_audio_peak(output_path)
    if peak_db <= AUDIO_SILENCE_THRESHOLD_DB:
        raise RuntimeError(
            "La traccia audio finale è silenziosa o quasi muta "
            f"(picco {peak_db:.1f} dBFS): {output_path}"
        )
    return codec, peak_db


def _report_render_progress(stage_progress: int, message: str) -> None:
    report_progress("rendering", 75, stage_progress, message)


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

    if not narration_path.is_file() or narration_path.stat().st_size == 0:
        raise RuntimeError(
            f"File della narrazione mancante o vuoto: {narration_path}"
        )
    narration_peak = _measure_audio_peak(narration_path)
    if narration_peak <= AUDIO_SILENCE_THRESHOLD_DB:
        raise RuntimeError(
            "Il WAV della narrazione è silenzioso o quasi muto "
            f"(picco {narration_peak:.1f} dBFS): {narration_path}"
        )
    _report_render_progress(
        5,
        f"Voce da mixare: {narration_path} "
        f"({narration_path.stat().st_size} byte; picco {narration_peak:.1f} dBFS).",
    )

    background_music = _select_background_music()
    if background_music is None:
        _report_render_progress(
            7,
            f"Nessuna musica valida in {MUSIC_DIRECTORY}; il render userà solo la voce.",
        )
    else:
        music_peak = _measure_audio_peak(background_music)
        if music_peak <= AUDIO_SILENCE_THRESHOLD_DB:
            raise RuntimeError(
                "La musica selezionata è silenziosa o quasi muta "
                f"(picco {music_peak:.1f} dBFS): {background_music}"
            )
        _report_render_progress(
            7,
            f"Musica da mixare: {background_music} "
            f"({background_music.stat().st_size} byte; picco {music_peak:.1f} dBFS; "
            "volume mix 10%).",
        )

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
        # "[video]subtitles=captions.ass[output]"
        f"[video]subtitles=filename='captions.ass':"
        f"fontsdir='{_escape_filter_path(CAPTION_FONT_DIRECTORY)}'[output]"
    )
    if background_music is None:
        # filters.append("[1:a]anull[finalaudio]")
        filters.append("[1:a]loudnorm=I=-16:TP=-1.5:LRA=7[finalaudio]")
    else:
        fade_duration = min(1.0, duration)
        fade_start = max(0.0, duration - fade_duration)
        filters.append(
            # "[1:a]volume=1.0[voice];"
            "[1:a]loudnorm=I=-16:TP=-1.5:LRA=7[voice];"
            f"[2:a]atrim=duration={duration:.3f},asetpts=PTS-STARTPTS,"
            f"volume=0.1,afade=t=out:st={fade_start:.3f}:d={fade_duration:.3f}[music];"
            "[voice][music]amix=inputs=2:duration=first:"
            "dropout_transition=0:normalize=0[finalaudio]"
        )
    filter_graph = ";".join(filters)

    # command = [
    #     os.environ.get("FFMPEG_EXECUTABLE", "ffmpeg"),
    #     "-hide_banner",
    #     "-loglevel",
    #     "error",
    #     "-y",
    #     "-i",
    #     str(video_path),
    #     "-i",
    #     str(narration_path),
    #     "-filter_complex",
    #     filter_graph,
    #     "-map",
    #     "[output]",
    #     "-map",
    #     "1:a:0",
    #     "-c:v",
    #     "libx264",
    #     "-preset",
    #     "veryfast",
    #     "-crf",
    #     "22",
    #     "-c:a",
    #     "aac",
    #     "-b:a",
    #     "192k",
    #     "-t",
    #     f"{duration:.3f}",
    #     "-movflags",
    #     "+faststart",
    #     str(output_path),
    # ]
    command = [
        os.environ.get("FFMPEG_EXECUTABLE", "ffmpeg"),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(narration_path),
        *(
            ["-stream_loop", "-1", "-i", str(background_music)]
            if background_music is not None
            else []
        ),
        "-filter_complex",
        filter_graph,
        "-map",
        "[output]",
        "-map",
        "[finalaudio]",
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
    ]
    for index, clip in enumerate(clips, start=1):
        _report_render_progress(
            min(25, 8 + index),
            f"Clip renderizzata {index}/{len(clips)}: "
            f"{clip.start:.2f}-{clip.end:.2f}s (score {clip.score:.2f}).",
        )
    _report_render_progress(
        26,
        "Mappa audio FFmpeg: input 1 = voce WAV normalizzata a -16 LUFS; "
        + (
            "input 2 = musica con volume al 10%."
            if background_music is not None
            else "nessuna musica, passthrough della voce."
        ),
    )
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=3600,
        cwd=output_path.parent,
    )
    codec, output_peak = _verify_rendered_audio(output_path)
    _report_render_progress(
        99,
        f"Verifica audio finale superata: codec {codec}, "
        f"picco {output_peak:.1f} dBFS in {output_path}.",
    )
