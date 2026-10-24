# 🎬 Text → Code → Video Studio — v3

**Any input → Free AI breakdown → Free AI scene images → Speaking character avatars → Ducked background music → Code + MP4**
**Plus: ⚡ Bulk Mode — 1 topic → 10 Shorts · 👤 Optional Google Sign-In + ☁️ Google Drive save**

## ✨ v3: Accounts & saving (new)

- **Optional Google login** (Guest mode always works). Sign-in is verified server-side; your characters, styles, projects, renders and draft are saved **per Google account**.
- **Auto-save**: your current work auto-saves every few seconds (browser + your account on the server) and is restored when you come back. Finished renders stay listed under *Your saved renders* even after server restarts.
- **Google Drive backup/restore**: one click backs up everything (including scene/avatar images) into a hidden folder in **your** Drive; restore it on any copy of the app. Rendered videos/ZIPs can be uploaded to a visible "Text to Video Studio" Drive folder.
- **Runs everywhere**: Windows `START_APP_WINDOWS.bat`, Linux/Mac script, Arena live preview, or Docker (`Dockerfile` / `render.yaml` included).
- Setup takes ~3 minutes once: see **[GOOGLE_SETUP.md](GOOGLE_SETUP.md)**. No client secret is used or needed.

> Reality check: login doesn't keep a hosting link alive (Arena sandbox links expire when the sandbox stops). Drive backup is what makes your **work** immortal: open the app anywhere → sign in → Restore.

100% free stack. No paid API anywhere:
- Breakdown AI: built-in offline engine, or your free Groq / Gemini / OpenRouter key
- Image AI: Pollinations free tier (no key) — scene backgrounds + character avatars, cached on disk
- Voices: Microsoft Edge-TTS free voices (EN-IN/US/UK, Telugu, Hindi, Tamil)
- Music: 5 built-in tracks **synthesized by the app itself** (royalty-free) or your own upload

## ✨ v2 Features

1. **🎨 AI image per scene** — each scene's `visual_prompt` becomes an AI background with Ken-Burns zoom/pan animation. Generate per-scene or all at once in Step 2, or auto-generate during render. Images are cached — generated once, reused forever.
2. **🎵 Background music + auto-ducking** — pick a built-in mood (Cinematic / Calm / Upbeat / Dark / Happy) or upload your mp3. Set volume + ducking: music automatically dips while a character speaks and swells in the gaps.
3. **🧑‍🎨 Speaking avatars** — generate a free AI avatar from a character's name + description (or upload your own image). While that character speaks, their circular avatar appears on screen with pulse rings + bobbing, plus a mini avatar in the header.
4. **⚡ Bulk: 1 topic → 10 Shorts** — one topic creates 10 different-angle Shorts (Shocking Fact, Myth Busted, How It Works, Origin Story…), all 9:16 with your style/voices/music. Render selected ones in the background and download individually or as one ZIP.

Plus everything from v1: any-format input (topic/prompt/raw text/dialogue script/list), custom styles (words or reference image), characters added one-by-one with described voices saved forever, downloadable generated Python code for every video, 16:9 + 9:16, Draft 720p / Full 1080p.

## Run it

```bash
cd text-to-video-app
pip install -r requirements.txt
python app.py            # or: uvicorn app:app --host 0.0.0.0 --port 8000
```
Open http://localhost:8000

## How to use

1. **Step 1 — Text:** paste a topic/prompt/script/dialogue (`NAME: line`). Pick format + style → **AI Breakdown**.
2. **Step 2 — Scenes:** edit text/speaker/animation/visual prompt. Hit **🎨 Generate AI Images for ALL scenes** (or per scene).
3. **Right panel — Characters:** add one by one. Describe the voice → auto-picked. **Generate Free AI Avatar**, preview the voice, Save. (Names must match your script. Demo `Narrator` + `King Vikram` with avatars are pre-saved.)
4. **Right panel — Style:** describe it or extract colours from a reference image. Save as preset.
5. **Step 3 — Generate:** choose AI backgrounds ON, avatars ON, music track + volume/ducking → **Generate Code** and/or **Render Video**.
6. **⚡ Bulk card:** topic → **Create 10 Short Scripts** → tick/edit → **Render Selected Shorts** → download videos or the ZIP.

## Measured speed (this machine, Draft 720p)

| Job | Time |
|---|---|
| 13-sec video, 2 voices + 2 AI backgrounds (cached) + 2 avatars + ducked music | ~10 sec render |
| Free AI image generation | ~6–60 sec each (free-tier queue; cached after) |
| Bulk: 2 Shorts (2 scenes each, voices+music+avatar) | ~20 sec total |
| Guide: 1-min Short | ~1–3 min |
| Guide: 10-min video | ~15–35 min (plus one-time image generation) |

**Honest note on free images:** Pollinations' anonymous free tier rate-limits bursts (HTTP 402). The app automatically paces requests and retries with backoff, and every successful image is cached. Best workflow: generate scene images in Step 2 *before* rendering, so renders stay fast. If an image fails, that scene falls back to your gradient style — the video never fails. Running the app locally uses your own IP quota.

## Project structure

```
app.py                 FastAPI server + API (auth, autosave, cloud backup, bulk jobs + ZIP)
core/auth.py           Google ID-token verification + signed sessions
core/breakdown.py      Free AI breakdown (offline + optional free LLM keys)
core/images.py         Free Pollinations images (paced, retried, cached)
core/music.py          Synthesized royalty-free music + auto-ducking mixer
core/bulk.py           1 topic -> 10 Shorts angle-engine (+ free LLM option)
core/renderer.py       Animation: Ken-Burns AI bg, karaoke text, speaking avatars
core/voices.py         Free Edge-TTS + description -> voice matching
core/style_engine.py   Style prompt / reference image -> palette
core/codegen.py        Scene plan -> runnable Python code
core/store.py          Users/characters/styles/projects/jobs/autosaves (data/db.json)
static/index.html      Studio UI (incl. Google Sign-In + Drive panel)
GOOGLE_SETUP.md        3-minute free Google Client ID guide
Dockerfile, render.yaml, Procfile   Deploy-anywhere files
outputs/               Videos, scene_images/, avatars/, music/, users/<account>/, bulk ZIPs
```

## Sample outputs (generated during testing)

- `outputs/test-v2.mp4` — 2 scenes, 2 voices, 2 AI backgrounds, 2 speaking avatars, ducked cinematic music
- `outputs/short-183ddc9cb4-01-*.mp4`, `...-02-*.mp4` — bulk-mode 9:16 Shorts + `outputs/bulk-183ddc9cb4.zip`
