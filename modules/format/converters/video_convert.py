"""
Video conversion using ffmpeg.
Supports codec, resolution, frame rate, audio codec, bitrate, cover image, and
cover-as-content (static image as video stream with audio).
"""
import os
import subprocess
import re
import shutil
from modules.i18n import _


def _find_ffmpeg():
    """Locate ffmpeg executable. Returns path or None."""
    for cmd in ["ffmpeg", "ffmpeg.exe"]:
        if shutil.which(cmd):
            return cmd
    # Check bundled ffmpeg
    script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    bundled = os.path.join(script_dir, "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.exists(bundled):
        return bundled
    return None


# Build ffmpeg at import time
_FFMPEG = _find_ffmpeg()


def is_available():
    return _FFMPEG is not None


def _get_video_info(input_path):
    """Get video duration, width, height using ffprobe. Returns (duration, width, height)."""
    ffprobe = (_FFMPEG.replace("ffmpeg", "ffprobe") if _FFMPEG else None)
    if not ffprobe:
        return None, None, None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            capture_output=True, text=True, timeout=30,
        )
        lines = result.stdout.strip().split('\n')
        w = int(lines[0]) if len(lines) > 0 and lines[0].isdigit() else None
        h = int(lines[1]) if len(lines) > 1 and lines[1].isdigit() else None
        dur = float(lines[2]) if len(lines) > 2 else None
        return dur, w, h
    except Exception:
        return None, None, None


def _get_duration(input_path):
    """Get video duration in seconds using ffprobe."""
    ffprobe = (_FFMPEG.replace("ffmpeg", "ffprobe") if _FFMPEG else None)
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            capture_output=True, text=True, timeout=30,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _parse_progress(line):
    """Parse ffmpeg progress line like 'time=00:01:23.45'. Returns (seconds, total_seconds)."""
    match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return h * 3600 + m * 60 + s
    return None


def convert_video(input_path, output_path, settings, progress_callback=None):
    """Convert a video file using ffmpeg.

    Args:
        input_path: Source video path
        output_path: Destination path (including extension)
        settings: dict with keys:
            video_codec, resolution, frame_rate, audio_codec, audio_bitrate,
            cover_path, cover_as_content, quality, bitrate
        progress_callback: callable(percent: float, status: str) called during conversion
            percent is 0.0-100.0, status is a short label string

    Returns:
        (success: bool, error_message: str or None)
    """
    if not _FFMPEG:
        return False, "ffmpeg not found. Please install ffmpeg and add it to your PATH."

    duration = _get_duration(input_path)  # may be None

    # --- Build ffmpeg args ---
    cmd = [_FFMPEG, "-y", "-i", input_path]

    # Cover image input
    cover_path = settings.get("cover_path", "")
    cover_as_content = settings.get("cover_as_content", False)
    has_cover = bool(cover_path and os.path.exists(cover_path))

    if has_cover:
        cmd.extend(["-i", cover_path])

    # Video codec
    vcodec = settings.get("video_codec", "h264")
    vcodec_map = {
        "h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9",
        "av1": "libaom-av1", "copy": "copy",
    }
    cmd.extend(["-c:v", vcodec_map.get(vcodec, "libx264")])

    # Quality / CRF
    quality = settings.get("quality", "high")
    crf_map = {"low": "30", "medium": "23", "high": "18", "lossless": "0"}
    if vcodec != "copy":
        cmd.extend(["-crf", crf_map.get(quality, "23")])

    # Resolution
    resolution = settings.get("resolution", "original")
    res_map = {"2160p": "3840:2160", "1080p": "1920:1080", "720p": "1280:720", "480p": "854:480"}
    if resolution in res_map:
        cmd.extend(["-vf", f"scale={res_map[resolution]}"])

    # Frame rate
    fps = settings.get("frame_rate", "original")
    if fps != "original" and fps.isdigit():
        cmd.extend(["-r", fps])

    # Audio codec
    acodec = settings.get("audio_codec", "aac")
    acodec_map = {"aac": "aac", "mp3": "libmp3lame", "opus": "libopus", "copy": "copy"}
    cmd.extend(["-c:a", acodec_map.get(acodec, "aac")])

    # Audio bitrate
    ab = settings.get("audio_bitrate", "")
    if ab and ab.strip() and ab.strip().isdigit():
        cmd.extend(["-b:a", f"{ab}k"])

    # Video bitrate
    vb = settings.get("bitrate", "")
    if vb and vb.strip() and vb.strip().isdigit():
        cmd.extend(["-b:v", f"{vb}k"])

    # Cover handling
    if cover_as_content and has_cover:
        # Get video dimensions for scaling
        _, vw, vh = _get_video_info(input_path)
        cover_fit = settings.get("cover_fit_mode", "blur")

        if cover_fit == "blur" and vw and vh:
            # Blur-fill: scale image to cover, blur it as background, overlay centered image
            filtergraph = (
                f"[1:v]scale={vw}:{vh}:force_original_aspect_ratio=increase,crop={vw}:{vh}"
                f",boxblur=20:20[bg];"
                f"[1:v]scale={vw}:{vh}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
            )
        elif cover_fit == "video_size" and vw and vh:
            # Letterbox: scale image to fit, pad to video dimensions
            filtergraph = (
                f"[1:v]scale={vw}:{vh}:force_original_aspect_ratio=decrease"
                f",pad={vw}:{vh}:(ow-iw)/2:(oh-ih)/2:black[v]"
            )
        else:
            # image_size or no video info: just pass the image through unchanged
            filtergraph = "[1:v]null[v]"

        cmd.extend([
            "-filter_complex", filtergraph,
            "-map", "[v]",
            "-map", "0:a:0",
        ])
    elif has_cover and not cover_as_content:
        # Attach cover as metadata only (mp4/mkv)
        cmd.extend([
            "-map", "0:v:0", "-map", "0:a:0",
            "-map", "1:v:0",
            "-disposition:v:1", "attached_pic",
        ])

    # Output
    cmd.append(output_path)

    # --- Run ffmpeg ---
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        last_percent = 0
        # Read stderr line by line for progress
        for line in proc.stderr:
            elapsed = _parse_progress(line)
            if elapsed is not None and duration and duration > 0:
                pct = min(99.0, (elapsed / duration) * 100)
                if pct - last_percent >= 1.0 or pct >= 99.0:
                    last_percent = pct
                    if progress_callback:
                        progress_callback(pct, _("转换中 {pct:.0f}%", pct=pct))
            elif "frame=" in line and progress_callback:
                # At least show we're working
                pass

        proc.wait(timeout=7200)  # 2 hour max

        if proc.returncode != 0:
            stderr_tail = ""
            try:
                stderr_lines = []
                for line in proc.stderr:
                    stderr_lines.append(line)
                stderr_tail = "".join(stderr_lines[-5:])
            except Exception:
                pass
            return False, f"ffmpeg exited with code {proc.returncode}: {stderr_tail}"

        if progress_callback:
            progress_callback(100.0, _("完成"))

        return True, None

    except FileNotFoundError:
        return False, "ffmpeg not found. Please install ffmpeg."
    except subprocess.TimeoutExpired:
        proc.kill()
        return False, "Conversion timed out (2 hours)."
    except Exception as ex:
        return False, str(ex)


def video_to_gif(input_path, output_path, settings=None, progress_callback=None):
    """Convert video to GIF (short clip, max 15 seconds)."""
    if not _FFMPEG:
        return False, "ffmpeg not found."
    s = settings or {}
    fps = s.get("frame_rate", "10")
    if fps == "original":
        fps = "10"
    res = s.get("resolution", "original")
    cmd = [_FFMPEG, "-y", "-i", input_path, "-t", "15"]
    if res in ("480p",):
        cmd.extend(["-vf", "fps={},scale=480:-1:flags=lanczos".format(fps)])
    else:
        cmd.extend(["-vf", f"fps={fps},scale=640:-1:flags=lanczos"])
    cmd.append(output_path)
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=True)
        return True, None
    except subprocess.CalledProcessError as ex:
        return False, ex.stderr.strip()[-300:]
    except Exception as ex:
        return False, str(ex)
