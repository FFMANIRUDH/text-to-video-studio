# 🔐 Google Login + Google Drive Save — 3-Minute Free Setup

This gives the app:
- **Sign in with Google** (optional — Guest mode always works)
- **Backup/Restore** of characters, styles, projects, scene images and your current progress into **your own Google Drive** (hidden app folder)
- **Save rendered videos/ZIPs** into a visible "Text to Video Studio" folder in your Drive

> Important reality check: Google login does **not** keep a server/link alive. If the Arena sandbox dies, the preview link dies with it. What Drive saving guarantees is that **your work is never lost**: open the app anywhere (your PC, a new Arena session, or a deployed copy), sign in, hit **Restore from Google Drive**, and everything comes back.

## Step 1 — Create a Google Cloud project (free)

1. Go to **https://console.cloud.google.com** and sign in with the Google account you want to use.
2. Top bar → project dropdown → **New Project** → name it e.g. `Text to Video Studio` → **Create** → make sure it's selected.

## Step 2 — Enable the Drive API

1. Left menu → **APIs & Services → Library**
2. Search **Google Drive API** → **Enable**.

## Step 3 — OAuth consent screen

1. Left menu → **Google Auth Platform** (or **APIs & Services → OAuth consent screen**) → **Get started**
2. App name: `Text to Video Studio`, User support email: your email → Audience: **External**
3. Contact email: your email → Create.
4. **Data Access / Scopes → Add scopes**, tick:
   - `openid`
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
   - `.../auth/drive.appdata`
   - `.../auth/drive.file`
5. If the app stays in **Testing** mode, go to **Audience → Test users → Add users** and add your own Gmail. (Or click **Publish app** so any of your accounts can sign in.)

## Step 4 — Create the OAuth Client ID

1. **Google Auth Platform → Clients** (or **APIs & Services → Credentials**) → **Create client / Create credentials → OAuth client ID**
2. Application type: **Web application**, name: `Text Video Web`
3. Under **Authorized JavaScript origins**, click **ADD URI** for *each* address you use:
   - `http://localhost:8000`  ← running on your PC
   - `http://127.0.0.1:8000`  ← running on your PC
   - `https://8000-iv7pkku7oqbkqymgurmqa.e2b.app`  ← current Arena preview (update this if your Arena sandbox ID ever changes — the app shows the exact current origin in the Account panel)
   - `https://YOUR-APP.onrender.com`  ← only if you deploy (use your real domain, no trailing slash/path)
   - `https://YOUR-USERNAME-text-to-video-studio.hf.space` + `https://huggingface.co`  ← if you deploy the web app on Hugging Face Spaces (see `DEPLOY_WEB_APP.md`)
4. **Authorized redirect URIs:** not required for this app's sign-in flow (it uses Google Identity Services). If Google insists, add the same origins.
5. **Create** → copy the **Client ID** — it looks like `1234567890-abcd....apps.googleusercontent.com`.
   - You do **not** need the Client Secret for this app. Never share the secret publicly.

## Step 5 — Paste it into the app

1. Open the app → right side → **👤 Account & Cloud Save**
2. Paste the Client ID → **✅ Use this Client ID** (saved in your browser)
3. The blue **Sign in with Google** button appears → sign in.
4. Click **⬆ Backup now to Google Drive** → approve Drive permission once.
5. Tick **Auto-backup** if you want it to silently re-backup after saves/renders (while Drive is connected).
6. Anywhere else: sign in with the same Google account → **⬇ Restore from Google Drive**.

For a permanent deployment you can instead set the environment variable `GOOGLE_CLIENT_ID` on the host (Render/Railway/etc.) — then every visitor gets the button automatically and the server locks sign-ins to your client.

## Running everywhere

| Where | How | Google origin to register |
|---|---|---|
| Windows PC | `START_APP_WINDOWS.bat` | `http://localhost:8000`, `http://127.0.0.1:8000` |
| Linux/Mac | `./start_app_linux_mac.sh` | same as above |
| Arena preview | Live Preview in this chat | exact `https://8000-....e2b.app` shown in the Account panel |
| Cloud (Docker) | `Dockerfile` / `render.yaml` included | your public `https://...` domain |

## Troubleshooting

- **"origin_mismatch" / Error 400:** the address in your browser's URL bar is not in *Authorized JavaScript origins* (step 4.3). Add it exactly — protocol + host + port, no path, no trailing `/`. Wait 1–2 minutes.
- **"access_blocked / app not verified":** your consent screen is in Testing and your Gmail isn't a Test user (step 3.5), or click *Advanced → Go to app* for your own project.
- **Drive permission errors:** Drive API not enabled (step 2), or scopes missing (step 3.4). Sign out, fix, sign in again.
- **Button doesn't appear:** Client ID not pasted (step 5.2), or you're offline (Google's script needs internet).
- **Videos didn't come back on Restore:** project backups store progress + images; rendered MP4s are saved separately with **🎥 Save last video to Drive** (they're too big for the progress backup). Your server copy also keeps every finished render under *Your saved renders*.
