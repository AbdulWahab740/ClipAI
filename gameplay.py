"""Find exciting moments in gameplay using loud sounds + fast motion."""
import subprocess
import wave

import numpy as np

from ffbin import FFMPEG


def _surprise(x, win=31):
    """How much each second stands out from the normal level around it."""
    if len(x) == 0:
        return x
    k = np.ones(win) / win
    base = np.convolve(np.pad(x, win // 2, mode="edge"), k, mode="valid")
    s = np.maximum(x - base, 0)
    return np.clip(s / (np.percentile(s, 95) + 1e-9), 0, 2)


def audio_loudness(wav_path):
    """Loudness for every second of the audio file (16 kHz mono wav)."""
    out = []
    with wave.open(str(wav_path), "rb") as w:
        sr = w.getframerate()
        while True:
            raw = w.readframes(sr)
            if len(raw) < sr:  # skip the last partial second
                break
            a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            out.append(np.sqrt(np.mean(a * a)))
    return np.array(out)


def motion_per_second(video_path, fps=2):
    """How much the picture changes, per second."""
    w, h = 64, 36
    cmd = [
        FFMPEG, "-v", "error", "-i", str(video_path),
        "-vf", f"fps={fps},scale={w}:{h},format=gray",
        "-f", "rawvideo", "-pix_fmt", "gray", "-",
    ]
    raw = subprocess.run(cmd, capture_output=True).stdout
    n = len(raw) // (w * h)
    if n < 2:
        return np.array([])
    frames = np.frombuffer(raw[: n * w * h], dtype=np.uint8).reshape(n, h, w).astype(np.float32)
    diff = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    diff = np.concatenate([[0], diff])
    usable = (len(diff) // fps) * fps
    return diff[:usable].reshape(-1, fps).mean(axis=1)


def excitement_score(video_path, wav_path):
    a = _surprise(audio_loudness(wav_path))
    m = _surprise(motion_per_second(video_path))
    n = max(len(a), len(m))
    if n == 0:
        return np.array([])
    a = np.pad(a, (0, n - len(a)))
    m = np.pad(m, (0, n - len(m)))
    score = 0.6 * a + 0.4 * m
    return np.convolve(np.pad(score, 1, mode="edge"), np.ones(3) / 3, mode="valid")


def find_peaks(score, count, min_gap=45):
    """Highest points that are at least min_gap seconds apart."""
    s = score.copy()
    peaks = []
    for _ in range(count):
        if len(s) == 0 or s.max() <= 0:
            break
        i = int(np.argmax(s))
        peaks.append((i, float(score[i])))
        s[max(0, i - min_gap): i + min_gap] = 0
    return peaks
