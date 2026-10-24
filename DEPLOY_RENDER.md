# 🚀 Deploy Free on Render (Permanent Web Link)

## Why Render now?

Hugging Face now requires a paid plan to create Docker/Gradio Spaces; only Static Spaces are free. Static hosting cannot run this app's Python video renderer. **Do not create the Hugging Face Space and do not subscribe just for this.**

Render can run the same Docker app on a **Free web service**. It is slower than your PC and sleeps after inactivity, but it gives you a permanent `https://...onrender.com` address without installing Python.

## Package to use

Use **`text-to-video-studio-github-render.zip`** — not the older Hugging Face ZIP.

Extract it. You should open the inside folder and see `app.py`, `Dockerfile`, and `render.yaml` together.

---

## Part 1 — Put the code on GitHub

Render deploys from a Git repository, so the code first goes to GitHub.

1. Go to **https://github.com** and sign in or create a free account.
2. Top-right **+ → New repository**.
3. Fill in:
   - **Repository name:** `text-to-video-studio`
   - **Visibility:** Public is easiest for the first deploy. Private also works if you authorize Render to access that one repository.
   - Do **not** add a README, .gitignore, or license during creation — the package already contains files.
4. Click **Create repository**.
5. On the empty repository page, click **uploading an existing file**.
6. On your PC, open the extracted package folder. Select **everything inside it** (`Ctrl + A`) and drag it into GitHub's upload box.
   - Important: GitHub's first page after upload must show `app.py`, `Dockerfile`, and `render.yaml` at the top level.
   - If you only see one folder called `text-to-video-studio` inside the repo, you dragged the outside folder. Delete/retry by dragging the *contents*.
7. Scroll down and click **Commit changes**.

## Part 2 — Create the free Render web service

1. Go to **https://render.com** → **Get Started** / **Sign in with GitHub** → authorize Render.
2. In the Render dashboard click **New + → Web Service**.
3. Choose **Build and deploy from a Git repository**.
4. Connect/select `text-to-video-studio`.
5. Confirm these settings:
   - **Name:** `text-to-video-studio`
   - **Branch:** `main`
   - **Root Directory:** leave blank
   - **Language / Runtime:** `Docker`
   - **Instance Type:** **Free** (confirm it says $0)
   - **Health Check Path** (Advanced): `/api/health`
6. Under Environment Variables, add:
   - `APP_SECRET` = any long random private text (30+ characters)
   - Leave Google variables for later.
7. Click **Create Web Service** / **Deploy**.
8. Wait for Logs to show the Docker build and then the service as **Live**. The first build can take several minutes.

Your permanent app address will look like:

```text
https://text-to-video-studio.onrender.com
```

The exact URL is shown at the top of the Render service page.

## Free Render limitations

- The free service **spins down after 15 minutes without traffic**; the next visit takes about a minute to wake.
- Its local filesystem is **ephemeral**: files can disappear when it spins down/restarts/redeploys.
- Therefore: sign in, finish important work, and use **Backup now to Google Drive**. Download finished MP4s or save them to Drive from the app.
- Free CPU/RAM is low. Use **Draft** quality and shorter scenes/Shorts on Render. Long 1080p renders are better on your PC.

## Google login on Render (after first deploy)

1. Create the Google OAuth Web Client ID using `GOOGLE_SETUP.md`.
2. Add this Authorized JavaScript origin:
   - `https://YOUR-ACTUAL-APP.onrender.com`
3. In Render → your service → **Environment**, add:
   - `GOOGLE_CLIENT_ID` = your Client ID
4. Save/redeploy and test Google sign-in in the app.
5. Only after sign-in works, optionally add:
   - `OWNER_EMAILS` = your Gmail address
   
   This locks saving/rendering to your Google account. Do not set it before sign-in is working or you will lock yourself out of actions.

## Troubleshooting

- **No open ports detected / deploy failed:** confirm Runtime is Docker and the repo root contains `Dockerfile`. The app binds to Render's `PORT`.
- **Service live but page loading:** free spin-up can take about a minute. Refresh once.
- **Render out of memory during a render:** use Draft quality, fewer/shorter scenes, turn off auto-generated images during render, then try again. The PC version remains best for heavy videos.
- **Characters/videos disappeared after restart:** expected on free ephemeral storage. Restore from Google Drive from the Account panel.
