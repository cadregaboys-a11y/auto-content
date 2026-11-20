import os
from pathlib import Path
from typing import Any


CAPTION_FONT_SIZE = 78
CAPTION_OUTLINE = 5
CAPTION_SHADOW = 2
CAPTION_ALIGNMENT = 2
CAPTION_MARGIN_L = 125
CAPTION_MARGIN_R = 125
CAPTION_MARGIN_V = 610
CAPTION_MAX_LINE_CHARACTERS = 20
CAPTION_MAX_EVENT_CHARACTERS = CAPTION_MAX_LINE_CHARACTERS * 2


def _caption_font_name() -> str:
    fonts_directory = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    try:
        installed_stems = {
            path.stem.casefold()
            for path in fonts_directory.iterdir()
            if path.is_file()
        }
    except OSError:
        return "Georgia"

    preferences = (
        ("Chiller", "chiller"),
        ("Creepster", "creepster"),
        ("Cinzel", "cinzel"),
        ("Impact", "impact"),
        ("Georgia", "georgia"),
    )
    for family, stem in preferences:
        if any(
            installed == stem or installed.startswith(f"{stem}-")
            for installed in installed_stems
        ):
            return family
    return "Georgia"


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{whole_seconds:02}.{fraction:02}"


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


# def _wrap_caption_words(words: list[str], active_index: int) -> str:
#     lines: list[str] = []
#     current_line: list[str] = []
#     line_characters = 0
#
#     for index, word in enumerate(words):
#         word = _escape_ass_text(word.strip())
#         if not word:
#             continue
#         additional_characters = len(word) + (1 if current_line else 0)
#         if (
#             current_line
#             and line_characters + additional_characters
#             > CAPTION_MAX_LINE_CHARACTERS
#         ):
#             lines.append(" ".join(current_line))
#             current_line = []
#             line_characters = 0
#
#         if index == active_index:
#             word = r"{\c&H0000FFFF&\b1}" + word + r"{\r}"
#         if current_line:
#             line_characters += 1
#         current_line.append(word)
#         line_characters += len(words[index].strip())
#
#     if current_line:
#         lines.append(" ".join(current_line))
#     return r"\N".join(lines)
def _wrap_caption_words(words: list[str]) -> str:
    lines: list[str] = []
    current_line: list[str] = []
    line_characters = 0

    for word in words:
        word = _escape_ass_text(word.strip())
        if not word:
            continue
        additional_characters = len(word) + (1 if current_line else 0)
        if (
            current_line
            and line_characters + additional_characters
            > CAPTION_MAX_LINE_CHARACTERS
        ):
            lines.append(" ".join(current_line))
            current_line = []
            line_characters = 0

        if current_line:
            line_characters += 1
        current_line.append(word)
        line_characters += len(word)

    if current_line:
        lines.append(" ".join(current_line))
    return r"\N".join(lines)


def _caption_word_groups(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []
    sentence_endings = (".", "!", "?", "…")

    for word in words:
        text = str(word["word"]).strip()
        if not text:
            continue
        candidate_texts = [
            str(item["word"]).strip() for item in current_group
        ] + [text]
        candidate_caption = _wrap_caption_words(candidate_texts)
        if current_group and (
            len(" ".join(candidate_texts)) > CAPTION_MAX_EVENT_CHARACTERS
            or candidate_caption.count(r"\N") >= 2
            or str(current_group[-1]["word"]).strip().endswith(sentence_endings)
        ):
            groups.append(current_group)
            current_group = []

        current_group.append(word)
        if text.endswith(sentence_endings):
            groups.append(current_group)
            current_group = []

    if current_group:
        groups.append(current_group)
    return groups


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
        # "WrapStyle: 2",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        # "Style: Default,Arial,62,&H00FFFFFF,&H000000FF,&H00000000,&H7F000000,1,0,0,0,100,100,0,0,1,4,1,2,70,70,170,1",
        (
            f"Style: Default,{_caption_font_name()},{CAPTION_FONT_SIZE},"
            "&H00FFFFFF,&H000000FF,&H00000000,&H7F000000,1,0,0,0,100,100,0,0,1,"
            f"{CAPTION_OUTLINE},{CAPTION_SHADOW},{CAPTION_ALIGNMENT},"
            f"{CAPTION_MARGIN_L},{CAPTION_MARGIN_R},{CAPTION_MARGIN_V},1"
        ),
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # for index, word in enumerate(words):
    #     first = max(0, index - 2)
    #     last = min(len(words), index + 3)
    #     caption_words = [
    #         _escape_ass_text(str(item["word"]).strip())
    #         for item in words[first:last]
    #     ]
    #     active = index - first
    #     caption_words[active] = (
    #         r"{\c&H0000FFFF&\b1}" + caption_words[active] + r"{\r}"
    #     )
    #     text = " ".join(part for part in caption_words if part)
    #     start = float(word["start"])
    #     end = float(word["end"])
    #     lines.append(
    #         f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,"
    #         f"{CAPTION_MARGIN_L},{CAPTION_MARGIN_R},{CAPTION_MARGIN_V},,{text}"
    #     )
    # for index, word in enumerate(words):
    #     first = max(0, index - 2)
    #     last = min(len(words), index + 3)
    #     caption_words = [
    #         str(item["word"]).strip()
    #         for item in words[first:last]
    #     ]
    #     active = index - first
    #     text = _wrap_caption_words(caption_words, active)
    #     start = float(word["start"])
    #     end = float(word["end"])
    #     lines.append(
    #         f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,"
    #         f"{CAPTION_MARGIN_L},{CAPTION_MARGIN_R},{CAPTION_MARGIN_V},,{text}"
    #     )
    caption_groups = _caption_word_groups(words)
    for index, group in enumerate(caption_groups):
        caption_words = [str(word["word"]).strip() for word in group]
        text = _wrap_caption_words(caption_words)
        start = float(group[0]["start"])
        end = float(group[-1]["end"])
        if index + 1 < len(caption_groups):
            next_start = float(caption_groups[index + 1][0]["start"])
            end = max(end, next_start)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,"
            f"{CAPTION_MARGIN_L},{CAPTION_MARGIN_R},{CAPTION_MARGIN_V},,{text}"
        )

    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return len(words)
