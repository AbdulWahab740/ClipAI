"""Find ffmpeg: use the system one, or the copy that comes with imageio-ffmpeg."""
import shutil


def _find():
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


FFMPEG = _find()
