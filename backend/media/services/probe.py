import json
import subprocess
from fractions import Fraction
from pathlib import Path

from django.conf import settings


class ProbeError(Exception):
    pass


def _to_float(value):
    if value in (
        None,
        "",
        "N/A",
    ):
        return None

    try:
        return float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _to_int(value):
    if value in (
        None,
        "",
        "N/A",
    ):
        return None

    try:
        return int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None


def _frame_rate(value):
    if not value or value == "0/0":
        return None

    try:
        return float(
            Fraction(value)
        )
    except (
        ValueError,
        ZeroDivisionError,
    ):
        return None


def probe_media_file(
    file_path: Path,
):
    command = [
        settings.FFPROBE_PATH,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
    except FileNotFoundError as exc:
        raise ProbeError(
            "ffprobe was not found."
        ) from exc

    except subprocess.TimeoutExpired as exc:
        raise ProbeError(
            "ffprobe timed out."
        ) from exc

    except subprocess.CalledProcessError as exc:
        message = (
            exc.stderr.strip()
            or "ffprobe failed."
        )

        raise ProbeError(
            message
        ) from exc

    try:
        raw = json.loads(
            result.stdout
        )
    except json.JSONDecodeError as exc:
        raise ProbeError(
            "ffprobe returned invalid JSON."
        ) from exc

    streams = raw.get(
        "streams",
        [],
    )

    format_info = raw.get(
        "format",
        {},
    )

    video_stream = next(
        (
            stream
            for stream in streams
            if (
                stream.get("codec_type")
                == "video"
                and stream
                .get(
                    "disposition",
                    {},
                )
                .get(
                    "attached_pic",
                    0,
                )
                != 1
            )
        ),
        None,
    )

    audio_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type")
            == "audio"
        ),
        None,
    )

    video_stream = (
        video_stream or {}
    )

    audio_stream = (
        audio_stream or {}
    )

    frame_rate = _frame_rate(
        video_stream.get(
            "avg_frame_rate"
        )
        or video_stream.get(
            "r_frame_rate"
        )
    )

    return {
        "duration_seconds": _to_float(
            format_info.get(
                "duration"
            )
        ),

        "container_format": (
            format_info.get(
                "format_name",
                "",
            )
        ),

        "bit_rate": _to_int(
            format_info.get(
                "bit_rate"
            )
        ),

        "video_codec": (
            video_stream.get(
                "codec_name",
                "",
            )
        ),

        "width": _to_int(
            video_stream.get(
                "width"
            )
        ),

        "height": _to_int(
            video_stream.get(
                "height"
            )
        ),

        "frame_rate": frame_rate,

        "audio_codec": (
            audio_stream.get(
                "codec_name",
                "",
            )
        ),

        "audio_channels": _to_int(
            audio_stream.get(
                "channels"
            )
        ),

        "raw": raw,
    }