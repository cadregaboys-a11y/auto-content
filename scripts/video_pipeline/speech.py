import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

from .events import report_progress


ELEVENLABS_REQUEST_TIMEOUT_SECONDS = 120


def _report_synthesis_progress(stage_progress: int, message: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
    with redirect_stdout(sys.stderr):
        report_progress(
            "elevenlabs_synthesis",
            47,
            stage_progress,
            f"[{timestamp}] {message}",
        )


def load_whisper_model() -> Any:
    try:
        import whisper
    except ImportError as error:
        raise RuntimeError(
            "Whisper non è installato. Esegui: python -m pip install -r requirements-video.txt"
        ) from error

    return whisper.load_model(os.environ.get("WHISPER_MODEL", "base"))


def transcribe(model: Any, media_path: Path, language: str, word_timestamps: bool) -> dict[str, Any]:
    return model.transcribe(
        str(media_path),
        language=language,
        word_timestamps=word_timestamps,
        verbose=False,
    )


def synthesize_narration(text: str, destination: Path) -> None:
    # report_progress("elevenlabs_synthesis", 47, 1, "Lettura configurazione")
    _report_synthesis_progress(1, "Lettura variabili ElevenLabs dall'ambiente del processo.")
    # api_key = os.environ.get("ELEVENLABS_API_KEY")
    # voice_id = os.environ.get("ELEVENLABS_VOICE_ID")
    api_key_raw = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id_raw = os.environ.get("ELEVENLABS_VOICE_ID", "")
    api_key = api_key_raw.strip()
    voice_id = voice_id_raw.strip()
    if not api_key or not voice_id:
        raise RuntimeError("Configura ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID nell'ambiente.")
    if any(character.isspace() for character in api_key):
        raise RuntimeError("ELEVENLABS_API_KEY contiene spazi o a capo interni.")
    if any(character.isspace() for character in voice_id):
        raise RuntimeError("ELEVENLABS_VOICE_ID contiene spazi o a capo interni.")

    whitespace_removed = api_key != api_key_raw or voice_id != voice_id_raw
    # report_progress("elevenlabs_synthesis", 47, 2, "Configurazione letta")
    _report_synthesis_progress(
        2,
        "Configurazione letta: API key=***; "
        f"voice_id={voice_id}; spazi esterni rimossi={'sì' if whitespace_removed else 'no'}.",
    )
    if len(text) > 5000:
        raise ValueError("Lo script supera il limite iniziale di 5000 caratteri.")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    request = Request(
        # f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        url,
        data=json.dumps(
            {
                "text": text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.75},
            }
        ).encode("utf-8"),
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )

    # report_progress("elevenlabs_synthesis", 47, 3, "Invio POST")
    _report_synthesis_progress(
        3,
        f"Invio POST {url} (voice_id={voice_id}; API key=***; "
        f"timeout={ELEVENLABS_REQUEST_TIMEOUT_SECONDS}s).",
    )
    try:
        # with urlopen(request, timeout=120) as response:
        with urlopen(request, timeout=ELEVENLABS_REQUEST_TIMEOUT_SECONDS) as response:
            response_headers = getattr(response, "headers", {})
            # report_progress("elevenlabs_synthesis", 47, 4, "Header risposta ricevuti")
            _report_synthesis_progress(
                4,
                "Header risposta ElevenLabs ricevuti: "
                f"HTTP {getattr(response, 'status', 'non indicato')}, "
                f"Content-Type={response_headers.get('Content-Type', 'non indicato')}, "
                f"Content-Length={response_headers.get('Content-Length', 'non indicata')}.",
            )
            destination.write_bytes(response.read())
    except HTTPError as error:
        # report_progress("elevenlabs_synthesis", 47, 4, "Header errore ricevuti")
        _report_synthesis_progress(
            4,
            "Header di errore ElevenLabs ricevuti: "
            f"HTTP {error.code}, "
            f"Content-Type={error.headers.get('Content-Type', 'non indicato') if error.headers else 'non indicato'}.",
        )
        # detail = error.read(2000).decode("utf-8", errors="replace")
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ElevenLabs ha restituito HTTP {error.code}: {detail}") from error
    except TimeoutError as error:
        message = (
            "Timeout della richiesta ElevenLabs "
            f"({ELEVENLABS_REQUEST_TIMEOUT_SECONDS}s): {error}"
        )
        # report_progress("elevenlabs_synthesis", 47, 4, message)
        _report_synthesis_progress(4, message)
        raise RuntimeError(message) from error
    except URLError as error:
        message = f"Connessione a ElevenLabs non riuscita: {error.reason}"
        if isinstance(error.reason, TimeoutError):
            message = (
                "Timeout della richiesta ElevenLabs "
                f"({ELEVENLABS_REQUEST_TIMEOUT_SECONDS}s): {error.reason}"
            )
        # report_progress("elevenlabs_synthesis", 47, 4, message)
        _report_synthesis_progress(4, message)
        raise RuntimeError(message) from error
