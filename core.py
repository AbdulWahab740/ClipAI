"""The heavy work: download, speech-to-text, picking clips, cutting clips.
Nothing here uses Streamlit, so it is easy to test."""
import base64
import json
import math
import re
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import gameplay

ERRORS = []  # every API error is kept here so the app can explain what went wrong
WORKERS = 3  # how many requests run at the same time


# ---------------------------------------------------------------- basics
def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def fmt_time(sec):
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def to_seconds(v):
    """Accept 83, "83.5" or "01:23"."""
    if isinstance(v, (int, float)):
        return float(v)
    sec = 0.0
    for p in str(v).strip().split(":"):
        sec = sec * 60 + float(p)
    return sec


def parse_json(text):
    text = re.sub(r"```json|```", "", text).strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"[\[{].*[\]}]", text, re.S)
    return json.loads(m.group(0) if m else text)


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def _retry_delay(msg, attempt):
    m = re.search(r"try again in (?:(\d+)m)?\s*([\d.]+)s", msg)
    if m:
        return int(m.group(1) or 0) * 60 + float(m.group(2)) + 1
    return 8 * (attempt + 1)


def explain_errors():
    """Turn raw API errors into short, friendly sentences."""
    text = " ".join(ERRORS).lower()
    out = []
    if "invalid_api_key" in text or "401" in text:
        out.append("Your Groq key looks wrong. Make a new one at console.groq.com/keys.")
    if "429" in text or "rate_limit" in text or "rate limit" in text:
        out.append("You reached the free Groq limit. Wait a few minutes, or pick a smaller "
                   "text model in Advanced settings.")
    if "model_not_found" in text or "404" in text:
        out.append("Groq does not offer the chosen model to your key. Pick another one "
                   "in Advanced settings.")
    if not out and ERRORS:
        out.append("Groq said: " + ERRORS[-1][:200])
    return out


# ---------------------------------------------------------------- video in
def download_youtube(url, out_dir, height=720, cookie_file=None, browser=None):
    import yt_dlp

    opts = {
        "format": f"bv*[height<={height}]+ba/b[height<={height}]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / f"%(id)s_{height}p.%(ext)s"),
        "quiet": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 4,  # faster downloads
        "socket_timeout": 30,
    }
    if cookie_file:
        opts["cookiefile"] = cookie_file
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        path = out_dir / f"{info['id']}_{height}p.mp4"
        if not path.exists():  # skip if we already have it
            ydl.download([url])
    return path


# ---------------------------------------------------------------- speech to text
def extract_audio_parts(video, out_dir, part_sec=600):
    """Small mp3 pieces (10 min each) so they upload fast and fit Groq's file limit."""
    run([
        "ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "libmp3lame", "-b:a", "32k", "-f", "segment",
        "-segment_time", str(part_sec), "-reset_timestamps", "1",
        str(out_dir / "part_%03d.mp3"),
    ])
    files = sorted(out_dir.glob("part_*.mp3"))
    return [(p, i * part_sec) for i, p in enumerate(files)]


def _transcribe_one(client, model, path, offset):
    for attempt in range(5):
        try:
            resp = client.audio.transcriptions.create(
                file=(path.name, path.read_bytes()),
                model=model,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                temperature=0.0,
            )
            segs = _get(resp, "segments") or []
            return [
                {"start": float(_get(s, "start")) + offset,
                 "end": float(_get(s, "end")) + offset,
                 "text": str(_get(s, "text")).strip()}
                for s in segs
            ]
        except Exception as e:
            msg = str(e)
            ERRORS.append(msg[:300])
            if any(k in msg for k in ("model_not_found", "404", "401", "invalid_api_key")):
                break
            delay = _retry_delay(msg, attempt)
            if delay > 90:  # daily limit, waiting will not help
                break
            time.sleep(delay)
    return None


def transcribe_parts(client, model, parts, on_progress):
    results = {}
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(_transcribe_one, client, model, p, off): i
                   for i, (p, off) in enumerate(parts)}
        for n, fut in enumerate(as_completed(futures), 1):
            results[futures[fut]] = fut.result()
            on_progress(n / len(parts))
    segments = []
    for i in range(len(parts)):
        segments += results.get(i) or []
    return segments


# ---------------------------------------------------------------- Groq chat
def groq_call(client, model, messages, json_mode):
    for attempt in range(4):
        try:
            kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
            resp = client.chat.completions.create(
                model=model, messages=messages, temperature=0.3, **kwargs
            )
            return parse_json(resp.choices[0].message.content)
        except Exception as e:
            msg = str(e)
            ERRORS.append(msg[:300])
            if "model_not_found" in msg or "404" in msg or "401" in msg:
                break
            if json_mode and ("response_format" in msg or "json" in msg.lower()):
                json_mode = False  # this model cannot do JSON mode
            elif "429" in msg or "rate" in msg.lower():
                delay = _retry_delay(msg, attempt)
                if delay > 90:
                    break
                time.sleep(delay)
            else:
                time.sleep(2)
    return None


PROMPT = """You find the best short clips in a podcast transcript.
Each line looks like: [start_seconds] text

Pick up to {n} moments. Each clip must:
- be between {lo} and {hi} seconds long
- make sense on its own, without the rest of the podcast
- have a strong hook: a bold opinion, a surprise, a good story, or a clear useful answer
- start at the beginning of a sentence and end at the end of a thought

Return ONLY JSON like this:
{{"clips": [{{"start": number, "end": number, "title": "short catchy title", "score": 1-10, "reason": "one short sentence"}}]}}
Use seconds from the transcript. If nothing is good, return {{"clips": []}}.

Transcript:
{text}
"""


def make_chunks(segments, chunk_seconds=480):
    chunks, current, chunk_start = [], [], None
    for s in segments:
        if chunk_start is None:
            chunk_start = s["start"]
        current.append(s)
        if s["end"] - chunk_start >= chunk_seconds:
            chunks.append(current)
            current, chunk_start = [], None
    if current:
        chunks.append(current)
    return chunks


def _ask_chunk(client, model, chunk, n, lo, hi):
    text = "\n".join(f"[{s['start']:.1f}] {s['text']}" for s in chunk)
    prompt = PROMPT.format(n=n, lo=lo, hi=hi, text=text)
    data = groq_call(client, model, [{"role": "user", "content": prompt}], True)
    if isinstance(data, dict):
        data = next((v for v in data.values() if isinstance(v, list)), [])
    return data if isinstance(data, list) else []


def find_clips(client, model, segments, num_clips, lo, hi, on_progress):
    chunks = make_chunks(segments)
    per_chunk = max(2, num_clips // max(len(chunks), 1) + 1)
    found = []
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(_ask_chunk, client, model, c, per_chunk, lo, hi) for c in chunks]
        for n, fut in enumerate(as_completed(futures), 1):
            found += fut.result()
            on_progress(n / len(chunks))
    return found


def snap(start, end, segments):
    """Move the cut to the nearest sentence edges."""
    s = min(segments, key=lambda x: abs(x["start"] - start))["start"]
    e = min(segments, key=lambda x: abs(x["end"] - end))["end"]
    return max(0.0, s - 0.3), e + 0.4


def pick_best(clips, n):
    clips = sorted(clips, key=lambda c: float(c.get("score") or 0), reverse=True)
    chosen = []
    for c in clips:
        if all(min(c["end"], k["end"]) - max(c["start"], k["start"]) <= 0.3 * (c["end"] - c["start"])
               for k in chosen):
            chosen.append(c)
        if len(chosen) == n:
            break
    return sorted(chosen, key=lambda c: c["start"])


def finalize_podcast(found, segments, num_clips, max_len):
    valid = []
    for c in found:
        try:
            st_, en_ = to_seconds(c["start"]), to_seconds(c["end"])
            en_ = min(en_, st_ + max_len)  # trim clips that are too long
            c["start"], c["end"] = snap(st_, en_, segments)
            if c["end"] - c["start"] >= 10:
                valid.append(c)
        except (KeyError, ValueError, TypeError):
            continue
    return pick_best(valid, num_clips)


def podcast_clips(client, text_model, whisper_model, video, work, num_clips, min_len, max_len,
                  on_progress):
    on_progress(0.02, "Getting the audio ready")
    parts = extract_audio_parts(video, work)
    if not parts:
        raise RuntimeError("Could not read any audio from this file.")
    segments = transcribe_parts(
        client, whisper_model, parts,
        lambda f: on_progress(0.05 + 0.45 * f, "Turning speech into text"))
    if not segments:
        raise RuntimeError("No speech found. " + " ".join(explain_errors()))
    found = find_clips(
        client, text_model, segments, num_clips, min_len, max_len,
        lambda f: on_progress(0.5 + 0.35 * f, "Finding the best moments"))
    return finalize_podcast(found, segments, num_clips, max_len)


# ---------------------------------------------------------------- gameplay
PROMPT_GAME = """These are {n} pictures from a short gameplay clip, in time order.
Judge the clip for social media. Score 1 to 10: does it look exciting, funny, skillful or surprising?
Give boring moments (menus, loading, walking, empty scenes) a low score.
Return ONLY JSON: {{"score": number, "title": "short catchy title", "reason": "one short sentence"}}"""


def grab_frames(video, start, end, n=4):
    frames = []
    tmp = Path(tempfile.mkdtemp())
    for k in range(n):
        t = start + (end - start) * (k + 0.5) / n
        out = tmp / f"f{k}.jpg"
        run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
             "-vf", "scale=512:-2", "-q:v", "5", str(out)])
        frames.append(base64.b64encode(out.read_bytes()).decode())
    return frames


def judge_clip(client, model, video, start, end):
    frames = grab_frames(video, start, end)
    content = [{"type": "text", "text": PROMPT_GAME.format(n=len(frames))}]
    for f in frames:
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}})
    out = groq_call(client, model, [{"role": "user", "content": content}], False)
    if isinstance(out, list) and out:
        out = out[0]
    return out if isinstance(out, dict) else {"score": 0, "title": "Clip", "reason": ""}


def gameplay_clips(client, vision_model, video, work, num_clips, min_len, max_len, on_progress):
    on_progress(0.02, "Listening for loud moments")
    wav = work / "audio.wav"
    run(["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    on_progress(0.15, "Watching for fast action")
    score = gameplay.excitement_score(video, wav)
    if len(score) == 0:
        return []
    length = (min_len + max_len) / 2
    peaks = gameplay.find_peaks(score, min(num_clips * 2, 20), min_gap=int(length))

    windows = []
    for sec, strength in peaks:
        start = max(0.0, sec - 0.4 * length)
        windows.append((sec, strength, start, min(float(len(score)), start + length)))

    results = []
    if vision_model:
        with ThreadPoolExecutor(WORKERS) as pool:
            futures = {pool.submit(judge_clip, client, vision_model, video, w[2], w[3]): w
                       for w in windows}
            for n, fut in enumerate(as_completed(futures), 1):
                sec, strength, start, end = futures[fut]
                info = fut.result()
                info["start"], info["end"] = start, end
                try:
                    info["rank"] = float(info.get("score", 0)) + strength
                except (TypeError, ValueError):
                    info["rank"] = strength
                results.append(info)
                on_progress(0.5 + 0.35 * n / len(windows), "The AI is checking the moments")
    else:
        for sec, strength, start, end in windows:
            results.append({"score": round(min(10.0, strength * 6), 1),
                            "title": f"Moment at {fmt_time(sec)}",
                            "reason": "Loud sound and fast action",
                            "start": start, "end": end, "rank": strength})
    results.sort(key=lambda c: c["rank"], reverse=True)
    return sorted(results[:num_clips], key=lambda c: c["start"])


# ---------------------------------------------------------------- cutting
def cut_clip(video, start, end, out_path, vertical=False):
    vf = ["-vf", "crop=ih*9/16:ih,scale=1080:1920"] if vertical else []
    run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-i", str(video), "-t", f"{end - start:.2f}",
         *vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_path)])


def cut_many(video, clips, out_dir, vertical, on_progress):
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / f"clip_{i}.mp4" for i in range(1, len(clips) + 1)]
    with ThreadPoolExecutor(WORKERS) as pool:
        futures = [pool.submit(cut_clip, video, c["start"], c["end"], p, vertical)
                   for c, p in zip(clips, paths)]
        for n, fut in enumerate(as_completed(futures), 1):
            fut.result()
            on_progress(n / len(clips))
    return paths