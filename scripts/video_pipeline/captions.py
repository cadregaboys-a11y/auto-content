from pathlib import Path
from typing import Any


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{whole_seconds:02}.{fraction:02}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def write_word_captions(transcription: dict[str, Any], destination: Path) -> int:
    words = [
        word
        for segment in transcription.get("segments", [])
        for word in segment.get("words", [])
        if word.get("word") and float(word.get("end", 0)) > float(word.get("start", 0))
    ]
    if not words:
        raise RuntimeError("Whisper non ha prodotto timestamp per le parole della narrazione.")

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 2",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Arial,62,&H00FFFFFF,&H000000FF,&H00000000,&H7F000000,1,0,0,0,100,100,0,0,1,4,1,2,70,70,170,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for index, word in enumerate(words):
        first = max(0, index - 2)
        last = min(len(words), index + 3)
        caption_words = [
            _escape_ass_text(str(item["word"]).strip())
            for item in words[first:last]
        ]
        active = index - first
        caption_words[active] = (
            r"{\c&H0000FFFF&\b1}" + caption_words[active] + r"{\r}"
        )
        text = " ".join(part for part in caption_words if part)
        start = float(word["start"])
        end = float(word["end"])
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
        )

    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(words)
