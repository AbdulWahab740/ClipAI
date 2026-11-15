# ClipAI

Turn a long podcast or gameplay video into short clips. Uses the free Groq API.

## Run on your computer
1. Install ffmpeg (Windows: `winget install Gyan.FFmpeg`, Mac: `brew install ffmpeg`).
2. `pip install -r requirements.txt`
3. `streamlit run app.py`
4. Paste your free Groq key (console.groq.com/keys) in the sidebar.

## Deploy on Streamlit Community Cloud (free)
1. Put these files in a GitHub repo: `app.py`, `core.py`, `gameplay.py`, `requirements.txt`,
   `packages.txt`, `.streamlit/config.toml`, `.gitignore`.
2. Go to share.streamlit.io, click **Create app**, pick your repo, and set the main file to `app.py`.
3. Click **Deploy**.

Optional: to give everyone your own key, add `GROQ_API_KEY = "gsk_..."` in the app's
**Settings > Secrets**. Anyone can then use up your free limit, so most people skip this.

## Good to know
- **Upload is the reliable way on a server.** YouTube often blocks downloads from hosting servers.
- Free servers have small memory. Big videos (over a few hundred MB) can crash the app.
  A server with more memory, like Hugging Face Spaces, helps.
- Files are deleted after 12 hours.
- Keep `yt-dlp` up to date. YouTube changes often and old versions break.
