import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

import streamlit as st
from groq import Groq

import core
st.set_page_config(page_title="ClipAI", page_icon="✂️", layout="wide")

# ---------------------------------------------------------------- look
st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1150px;}
footer {visibility: hidden;}
.hero {padding: 1.6rem 1.8rem; border-radius: 18px; margin-bottom: 1.2rem;
       background: linear-gradient(135deg, rgba(124,92,255,.35), rgba(0,200,255,.18));
       border: 1px solid rgba(255,255,255,.08);}
.hero h1 {margin: 0; font-size: 2.3rem; letter-spacing: -.5px;}
.hero p {margin: .4rem 0 0 0; opacity: .85; font-size: 1.05rem;}
.step {font-weight: 700; font-size: 1.05rem; margin: 1.2rem 0 .4rem 0;}
.step span {background: #7C5CFF; color: white; border-radius: 50%; padding: 2px 9px;
            margin-right: 8px; font-size: .9rem;}
.badge {display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem;
        font-weight: 700; color: #0B0F1A;}
.good {background: #4ADE80;} .ok {background: #FBBF24;} .low {background: #94A3B8;}
.clip-title {font-weight: 700; font-size: 1.05rem; margin: .5rem 0 .2rem 0;}
.muted {opacity: .65; font-size: .85rem;}
div.stButton > button[kind="primary"] {border-radius: 12px; font-weight: 700; padding: .7rem 1rem;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
  <h1>✂️ ClipAI</h1>
  <p>Drop in a long video. Get the best short clips, ready to post.</p>
</div>
""", unsafe_allow_html=True)

if not shutil.which("ffmpeg"):
    st.error("ffmpeg is not installed. Windows: run `winget install Gyan.FFmpeg` and open a new "
             "terminal. Mac: `brew install ffmpeg`. Linux: `sudo apt install ffmpeg`.")
    st.stop()

# ---------------------------------------------------------------- folders
BASE = Path(__file__).parent
DOWNLOADS, CLIPS = BASE / "downloads", BASE / "clips"
DOWNLOADS.mkdir(exist_ok=True)
CLIPS.mkdir(exist_ok=True)


@st.cache_resource
def cleanup_old(hours=12):
    """Keep the disk small on a hosted server: delete files older than 12 hours."""
    cutoff = time.time() - hours * 3600
    for folder in (DOWNLOADS, CLIPS):
        for p in folder.rglob("*"):
            if p.is_file() and p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
    return True


cleanup_old()


# ---------------------------------------------------------------- Groq models
@st.cache_data(show_spinner=False, ttl=3600)
def list_models(key):
    return sorted(m.id for m in Groq(api_key=key).models.list().data)


TEXT_PREFS = ["llama-3.3-70b-versatile", "openai/gpt-oss-120b", "llama-3.1-8b-instant",
              "openai/gpt-oss-20b", "moonshotai/kimi-k2-instruct", "qwen/qwen3-32b"]
NOT_TEXT = ("whisper", "guard", "tts", "orpheus", "playai", "safeguard", "embed", "distil")
NO_PICTURE = "None (sound + motion only)"

try:
    secret_key = st.secrets.get("GROQ_API_KEY", "")
except Exception:
    secret_key = ""

# ---------------------------------------------------------------- sidebar
text_model = vision_model = whisper_model = None
cookie_file = browser = None
yt_height = 720

with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input("Groq API key", type="password", value=secret_key,
                            placeholder="gsk_...", help="Free. Your key is not saved.")
    st.link_button("Get a free key", "https://console.groq.com/keys", use_container_width=True)

    models = []
    if api_key:
        try:
            models = list_models(api_key)
            st.success("Key works ✓")
        except Exception:
            st.error("This key does not work. Check it and try again.")

    with st.expander("Advanced"):
        if models:
            texts = [m for m in models if not any(k in m for k in NOT_TEXT)]
            pictures = [m for m in texts if any(k in m for k in ("llama-4", "vision", "scout", "maverick"))]
            whispers = [m for m in models if "whisper" in m]
            default = next((m for m in TEXT_PREFS if m in texts), None)
            text_model = st.selectbox("Text model", texts, index=texts.index(default) if default else 0)
            choice = st.selectbox("Picture model (gameplay)", [NO_PICTURE] + pictures,
                                  index=1 if pictures else 0)
            vision_model = None if choice == NO_PICTURE else choice
            if whispers:
                best = next((m for m in whispers if "turbo" in m), whispers[0])
                whisper_model = st.selectbox("Speech model", whispers, index=whispers.index(best))
        yt_height = st.selectbox("YouTube quality", [480, 720, 1080], index=1,
                                 format_func=lambda h: f"{h}p")
        st.markdown("**YouTube login** (only for age-restricted videos)")
        cookies_upload = st.file_uploader("cookies.txt", type=["txt"])
        if cookies_upload:
            cookie_path = Path(tempfile.gettempdir()) / f"cookies_{uuid.uuid4().hex[:6]}.txt"
            cookie_path.write_bytes(cookies_upload.getvalue())
            cookie_file = str(cookie_path)
        else:
            use_browser = st.selectbox("Or read a browser (local only)",
                                       ["Off", "firefox", "edge", "chrome", "brave"])
            browser = None if use_browser == "Off" else use_browser

# ---------------------------------------------------------------- step 1: video
st.markdown('<div class="step"><span>1</span>What are we clipping?</div>', unsafe_allow_html=True)
mode = st.radio("Type", ["🎙️ Podcast / talking", "🎮 Gameplay / action"], horizontal=True,
                label_visibility="collapsed")
is_game = mode.startswith("🎮")

tab_up, tab_link = st.tabs(["📁 Upload a video", "🔗 YouTube link"])
with tab_up:
    upload = st.file_uploader("Video file", type=["mp4", "mov", "mkv", "webm"],
                              label_visibility="collapsed")
with tab_link:
    yt_url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...",
                           label_visibility="collapsed")
    st.caption("Tip: on a hosted server YouTube often blocks downloads. Uploading always works.")

# ---------------------------------------------------------------- step 2: options
st.markdown('<div class="step"><span>2</span>Pick your options</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns([1, 1, 1])
num_clips = c1.slider("How many clips", 3, 15, 6)
min_len, max_len = c2.slider("Clip length (seconds)", 20, 120, (30, 75))
vertical = c3.toggle("Vertical 9:16 (Reels / Shorts)", value=False)

st.markdown('<div class="step"><span>3</span>Go</div>', unsafe_allow_html=True)
go = st.button("✨ Find clips", type="primary", use_container_width=True)


# ---------------------------------------------------------------- run
def run_job():
    if not api_key:
        st.error("Add your Groq API key in the sidebar first. It is free.")
        return
    if not upload and not yt_url:
        st.error("Upload a video or paste a YouTube link.")
        return
    if not text_model or (not is_game and not whisper_model):
        st.error("Could not load Groq models. Check your key in the sidebar.")
        return

    core.ERRORS.clear()
    t0 = time.time()
    work = Path(tempfile.mkdtemp())
    client = Groq(api_key=api_key)
    uploaded_copy = None

    status = st.status("Working on it...", expanded=True)
    bar = status.progress(0.0)
    label = status.empty()

    def on_progress(frac, text):
        bar.progress(min(max(frac, 0.0), 1.0))
        label.write(f"**{text}...**")

    try:
        on_progress(0.0, "Getting your video")
        if upload:
            uploaded_copy = DOWNLOADS / f"{uuid.uuid4().hex[:6]}_{Path(upload.name).name}"
            uploaded_copy.write_bytes(upload.getbuffer())
            video = uploaded_copy
        else:
            video = core.download_youtube(yt_url, DOWNLOADS, yt_height, cookie_file, browser)

        if is_game:
            best = core.gameplay_clips(client, vision_model, video, work, num_clips,
                                       min_len, max_len, on_progress)
        else:
            best = core.podcast_clips(client, text_model, whisper_model, video, work,
                                      num_clips, min_len, max_len, on_progress)
        if not best:
            status.update(label="No good clips found", state="error")
            for msg in core.explain_errors():
                st.error(msg)
            st.warning("Try a different video, more clips, or a wider clip length.")
            return

        out_dir = CLIPS / f"{video.stem[:30]}_{uuid.uuid4().hex[:4]}"
        paths = core.cut_many(video, best, out_dir, vertical,
                              lambda f: on_progress(0.85 + 0.14 * f, "Cutting the clips"))
        zip_path = out_dir / "all_clips.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
            for p in paths:
                z.write(p, p.name)

        st.session_state["result"] = {
            "clips": [dict(c, path=str(p)) for c, p in zip(best, paths)],
            "zip": str(zip_path),
            "seconds": time.time() - t0,
            "folder": str(out_dir),
        }
        status.update(label=f"Done in {time.time() - t0:.0f} seconds", state="complete",
                      expanded=False)
    except Exception as e:
        status.update(label="Something went wrong", state="error")
        text = str(e)
        if "Sign in to confirm" in text or "age" in text.lower() and "confirm" in text.lower():
            st.error("YouTube wants a login for this video. Open Advanced in the sidebar and "
                     "add a cookies.txt file, or download the video and upload it here.")
        elif "Could not copy" in text and "cookie" in text:
            st.error("Could not read the browser login. Close the browser fully, try Firefox, "
                     "or use a cookies.txt file.")
        elif "429" in text or "HTTP Error 403" in text or "bot" in text.lower():
            st.error("YouTube blocked this download. Download the video yourself and upload it.")
        else:
            st.error(f"{text[:400]}")
    finally:
        shutil.rmtree(work, ignore_errors=True)
        if uploaded_copy:
            uploaded_copy.unlink(missing_ok=True)  # you already have the original


if go:
    st.session_state.pop("result", None)
    run_job()

# ---------------------------------------------------------------- results
res = st.session_state.get("result")
if res:
    clips = res["clips"]
    st.divider()
    h1, h2 = st.columns([3, 1])
    h1.subheader(f"🎬 {len(clips)} clips ready")
    h1.caption(f"Made in {res['seconds']:.0f} seconds · saved in `{res['folder']}`")
    if Path(res["zip"]).exists():
        h2.download_button("⬇️ Download all (ZIP)", Path(res["zip"]).read_bytes(),
                           file_name="clips.zip", use_container_width=True)

    cols = st.columns(2)
    for i, c in enumerate(clips):
        path = Path(c["path"])
        if not path.exists():
            continue
        try:
            score = float(c.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        css = "good" if score >= 8 else "ok" if score >= 6 else "low"
        with cols[i % 2].container(border=True):
            st.video(str(path))
            st.markdown(f'<div class="clip-title">{c.get("title", "Clip")}</div>'
                        f'<span class="badge {css}">Score {score:g}</span>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="muted">{core.fmt_time(c["start"])} to '
                        f'{core.fmt_time(c["end"])} · {c.get("reason", "")}</div>',
                        unsafe_allow_html=True)
            st.download_button("Download", path.read_bytes(), file_name=path.name,
                               key=f"dl{i}", use_container_width=True)

with st.expander("How does this work?"):
    st.markdown(
        "- **Podcast:** the app turns speech into text, and the AI picks the moments with a "
        "strong hook.\n"
        "- **Gameplay:** the app finds loud and fast moments, and the AI checks pictures from them.\n"
        "- Each clip is cut at the end of a sentence so it does not stop mid-word."
    )