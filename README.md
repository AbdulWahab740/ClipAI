<div align="center">

# ✂️ ClipAI

**Drop in a long video. Get the best short clips, ready to post.**

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Groq](https://img.shields.io/badge/AI-Groq%20(free)-F55036)
![ffmpeg](https://img.shields.io/badge/Video-ffmpeg-007808?logo=ffmpeg&logoColor=white)

</div>

---

## ✨ What it does

Give ClipAI a one hour podcast or a long gameplay video. It finds the best moments and cuts them into short clips for you.

| | 🎙️ Podcast mode | 🎮 Gameplay mode |
|---|---|---|
| **Finds moments by** | What people say | Loud sounds and fast action |
| **How** | Speech to text, then AI reads it | Sound and motion check, then AI looks at pictures |
| **Cuts** | At the end of a sentence | Around each exciting peak |

**Also included**
- 📱 Vertical 9:16 option for Reels, Shorts and TikTok
- ⬇️ Download each clip, or all of them in one ZIP
- 🆓 Runs on the free Groq plan
- ⚡ Fast: several requests and cuts run at the same time

---

## 🚀 Quick start

**1. Install ffmpeg**

| System | Command |
|---|---|
| Windows | `winget install Gyan.FFmpeg` (then open a new terminal) |
| Mac | `brew install ffmpeg` |
| Linux | `sudo apt install ffmpeg` |

**2. Install and run**

```bash
pip install -r requirements.txt
streamlit run app.py
```

**3. Add your key**

Get a free key at [console.groq.com/keys](https://console.groq.com/keys) and paste it in the sidebar.

---

## 🖱️ How to use it

1. **Choose the type:** Podcast or Gameplay.
2. **Add the video:** upload a file, or paste a YouTube link.
3. **Pick options:** how many clips, how long, vertical or not.
4. **Click ✨ Find clips** and wait. Your clips show up as cards.

---

## ☁️ Deploy it (free)

Use Streamlit Community Cloud:

1. Put these files in a GitHub repo:
   `app.py` · `core.py` · `gameplay.py` · `requirements.txt` · `packages.txt` · `.streamlit/config.toml` · `.gitignore`
2. Go to [share.streamlit.io](https://share.streamlit.io) and click **Create app**.
3. Choose your repo and set the main file to `app.py`.
4. Click **Deploy**.

> 💡 **Optional:** add `GROQ_API_KEY = "gsk_..."` in **Settings → Secrets** so visitors don't need a key. Anyone can then use up your free limit, so most people skip this.

---

## ⚠️ Good to know

- **Upload is the reliable way on a server.** YouTube often blocks downloads from hosting servers.
- **Age-restricted videos:** add a `cookies.txt` file in **Advanced** in the sidebar, or upload the video yourself. Treat `cookies.txt` like a password.
- **Free servers have small memory.** Very big videos can crash the app.
- **Free Groq limits are small.** One long podcast uses a good part of your daily limit. If you hit it, wait a few minutes or pick a smaller model in **Advanced**.
- **Files are deleted after 12 hours** to keep the disk small.
- **Keep `yt-dlp` up to date.** YouTube changes often, and old versions break.

---

## 🗂️ Project files

| File | What it does |
|---|---|
| `app.py` | The page you see (design and buttons) |
| `core.py` | Download, speech to text, picking clips, cutting clips |
| `gameplay.py` | Finds loud and fast moments |
| `requirements.txt` | Python packages |
| `packages.txt` | System packages for the server (ffmpeg) |
| `.streamlit/config.toml` | Dark theme and upload size |

---

## 📌 A note on copyright

Only clip videos you own or have permission to use. Posting other people's content can lead to takedowns.

<div align="center">

Made with ❤️ using Streamlit, Groq and ffmpeg

</div>
