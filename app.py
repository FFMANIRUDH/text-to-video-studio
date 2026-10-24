"""
Text -> Code -> Video Studio (v3)
Any input (topic / prompt / raw text / dialogue script)
  -> FREE AI breakdown -> FREE AI scene images + character avatars
  -> background music with auto-ducking -> generated code + MP4 (16:9 / 9:16)
  -> BULK: 1 topic -> 10 Shorts (+ ZIP)
  -> v3: optional Google Sign-In, per-account saving, auto-save,
         Google Drive backup/restore of all progress.

Login is OPTIONAL (guest mode works fully). Your progress is auto-saved
in the browser + on the server per account, and can be backed up to
your own Google Drive from the Account panel. See GOOGLE_SETUP.md.

Run:  uvicorn app:app --host 0.0.0.0 --port 8000     (or: python app.py)
Env:  PORT, GOOGLE_CLIENT_ID (optional), APP_SECRET (optional)
"""
import base64, hashlib, io, mimetypes, os, re, threading, time, uuid, zipfile
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core import store, breakdown as bd, voices as voice_mod, style_engine, codegen, auth as auth_mod
from core import images as images_mod, music as music_mod, bulk as bulk_mod

BASE = Path(__file__).resolve().parent
OUT = BASE / "outputs"; OUT.mkdir(exist_ok=True)
for sub in ("previews", "scene_images", "avatars", "music", "users"):
    (OUT / sub).mkdir(exist_ok=True)

app = FastAPI(title="Text -> Code -> Video Studio")

# --------------------------------------------------------------------- users
def current_user(request: Request) -> dict:
    token = auth_mod.extract_token(request.headers, request.cookies)
    user = auth_mod.parse_session(token) if token else None
    return user or dict(auth_mod.GUEST)


@app.middleware("http")
async def owner_lock(request: Request, call_next):
    """Optional owner-lock for public hosting (e.g. a public Hugging Face Space).
    If OWNER_EMAILS is set (comma-separated Gmail addresses), only those signed-in
    Google accounts may save/render/change anything. Leave unset for open/guest mode."""
    owners = {e.strip().lower() for e in os.environ.get("OWNER_EMAILS", "").split(",") if e.strip()}
    path = request.url.path
    if owners and request.method not in ("GET", "HEAD", "OPTIONS") and path.startswith("/api/") \
            and path not in ("/api/auth/google", "/api/auth/logout"):
        user = current_user(request)
        if user.get("guest") or (user.get("email", "").lower() not in owners):
            return JSONResponse({"detail": "This studio is locked to its owner. Sign in with the owner's Google account to save or render."}, status_code=401)
    return await call_next(request)


def safe_owner(owner: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(owner or "guest"))[:80] or "guest"


def user_dir(owner: str) -> Path:
    p = OUT / "users" / safe_owner(owner)
    p.mkdir(parents=True, exist_ok=True)
    return p


def visible(items, owner):
    """Signed-in users see their own + guest/legacy items; guests see guest items.
    If the account has its own copy with the same name, the guest preset is hidden
    (so restoring/cloning never shows duplicates)."""
    items = items or []
    own_names = {str(x.get("name", "")).lower() for x in items
                 if (x.get("owner_id") or "guest") == owner and owner != "guest" and x.get("name")}
    out = []
    for x in items:
        o = x.get("owner_id") or "guest"
        if o not in (owner, "guest"):
            continue
        if o == "guest" and owner != "guest" and str(x.get("name", "")).lower() in own_names:
            continue
        out.append(x)
    return out


def ensure_can_touch(collection, item_id, owner):
    old = store.find(collection, item_id)
    if old and (old.get("owner_id") or "guest") not in (owner, "guest"):
        raise HTTPException(403, "That item belongs to another account.")
    return old


# ----------------------------------------------------------------------- jobs
JOBS = {}


def _persist_job(job):
    try:
        store.upsert("jobs", dict(job))
    except Exception:
        pass


def job_update(job_id, **kw):
    if job_id in JOBS:
        JOBS[job_id].update(kw)
        _persist_job(JOBS[job_id])


def _load_jobs():
    changed = False
    for rec in store.load().get("jobs", []):
        if rec.get("status") in ("queued", "running"):
            rec = {**rec, "status": "error", "message": "Interrupted (server restarted). Your finished files are safe — just render again."}
            changed = True
        JOBS[rec["id"]] = rec
        if changed:
            _persist_job(rec)
    # Legacy renders (made before job-history existed) still appear as saved files
    known = {j.get("output") for j in JOBS.values()}
    for mp4 in sorted(OUT.glob("*.mp4")):
        rel = f"/outputs/{mp4.name}"
        if rel in known:
            continue
        jid = "legacy-" + hashlib.md5(mp4.name.encode()).hexdigest()[:10]
        poster = mp4.with_suffix(".jpg")
        rec = {"id": jid, "type": "single", "owner_id": "guest", "title": mp4.stem,
               "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(mp4.stat().st_mtime)),
               "status": "done", "progress": 100, "message": "Saved render (from earlier version)",
               "output": rel, "poster": f"/outputs/{poster.name}" if poster.exists() else ""}
        JOBS[jid] = rec
        _persist_job(rec)


_load_jobs()


class BreakdownReq(BaseModel):
    text: str
    format: str = "16:9"
    provider: str = "offline"
    api_key: str = ""
    model: str = ""


class RenderReq(BaseModel):
    title: str = ""
    scenes: list = []
    style: dict = {}
    characters: list = []
    format: str = "16:9"
    quality: str = "draft"
    voice: bool = True
    use_images: bool = True
    generate_images: bool = False
    show_avatars: bool = True
    music: dict = {}


class BulkPlanReq(BaseModel):
    topic: str
    count: int = 10
    provider: str = "offline"
    api_key: str = ""
    model: str = ""


class BulkRenderReq(RenderReq):
    items: list = []


class GoogleAuthReq(BaseModel):
    id_token: str
    client_id: str = ""


class AutosaveReq(BaseModel):
    draft: dict = {}
    updated_at: str = ""


def _opts(req: RenderReq):
    return {"voice": req.voice, "use_images": req.use_images, "generate_images": req.generate_images,
            "show_avatars": req.show_avatars, "music": req.music or {}}


def _music_uploads(owner):
    ups = list(music_mod.list_uploads())  # legacy/global
    folder = user_dir(owner) / "music"
    if folder.exists():
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a"):
                ups.append({"name": p.name, "url": f"/outputs/users/{safe_owner(owner)}/music/{p.name}"})
    return ups


@app.get("/api/health")
def health():
    return {"ok": True, "app": "text-to-code-video", "version": 3}


@app.get("/api/auth/config")
def auth_config():
    return {"google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "drive_scopes": "https://www.googleapis.com/auth/drive.appdata https://www.googleapis.com/auth/drive.file"}


@app.post("/api/auth/google")
def auth_google(req: GoogleAuthReq):
    try:
        profile = auth_mod.verify_google_id_token(req.id_token, req.client_id)
    except Exception as e:
        raise HTTPException(401, str(e))
    user = store.upsert("users", {**profile, "last_login": time.strftime("%Y-%m-%dT%H:%M:%S")})
    token = auth_mod.make_session(user)
    public = {"id": user["id"], "email": user.get("email", ""), "name": user.get("name", ""),
              "picture": user.get("picture", ""), "guest": False}
    resp = JSONResponse({"user": public, "token": token})
    resp.set_cookie("ttv_session", token, max_age=30 * 86400, httponly=True, samesite="lax")
    return resp


@app.get("/api/auth/me")
def auth_me(request: Request):
    return {"user": current_user(request)}


@app.post("/api/auth/logout")
def auth_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("ttv_session")
    return resp


@app.get("/api/bootstrap")
def bootstrap(request: Request):
    user = current_user(request)
    owner = user["id"]
    data = store.load()
    jobs = visible(sorted(JOBS.values(), key=lambda j: j.get("created_at", ""), reverse=True), owner)[:20]
    return {"user": user,
            "characters": visible(data["characters"], owner),
            "styles": visible(data["styles"], owner),
            "voices": voice_mod.VOICES,
            "projects": visible(data["projects"], owner),
            "jobs": jobs,
            "autosave": store.get_autosave(owner),
            "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
            "music": {"builtins": music_mod.BUILTINS, "uploads": _music_uploads(owner)}}


# ------------------------------------------------------------------ autosave
@app.post("/api/autosave")
def api_autosave(req: AutosaveReq, request: Request):
    return store.set_autosave(current_user(request)["id"], req.draft, req.updated_at)


@app.get("/api/autosave")
def api_get_autosave(request: Request):
    return store.get_autosave(current_user(request)["id"])


# ------------------------------------------------------------- cloud backup
def _collect_output_urls(obj, acc):
    if isinstance(obj, str):
        if obj.startswith("/outputs/") and not obj.endswith((".mp4", ".zip")):
            acc.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_output_urls(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_output_urls(v, acc)


@app.get("/api/cloud/export")
def cloud_export(request: Request):
    """Everything needed to restore this account anywhere (images embedded)."""
    user = current_user(request)
    owner = user["id"]
    data = store.load()
    payload = {
        "app": "text-to-code-video-studio", "version": 3,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "user": {"email": user.get("email", ""), "name": user.get("name", "")},
        "characters": visible(data["characters"], owner),
        "styles": visible(data["styles"], owner),
        "projects": visible(data["projects"], owner),
        "autosave": store.get_autosave(owner),
        "jobs": visible(sorted(JOBS.values(), key=lambda j: j.get("created_at", ""), reverse=True), owner)[:30],
        "assets": {}, "asset_warnings": [],
    }
    urls = set()
    _collect_output_urls(payload, urls)
    total = 0
    for url in sorted(urls):
        p = BASE / url.lstrip("/")
        if not p.exists():
            continue
        size = p.stat().st_size
        if size > 4_000_000 or total + size > 25_000_000:
            payload["asset_warnings"].append(f"Skipped large file in backup: {url}")
            continue
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if not (mime.startswith("image/") or mime.startswith("audio/")):
            continue
        total += size
        payload["assets"][url] = {"mime": mime, "size": size,
                                  "data_url": f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()}
    return payload


def _materialize_assets(owner, assets):
    """Write embedded backup assets back to disk for this account. Returns old->new URL map."""
    mapping = {}
    folder = user_dir(owner) / "restored"
    folder.mkdir(parents=True, exist_ok=True)
    items = assets.items() if isinstance(assets, dict) else []
    for old_url, info in list(items)[:60]:
        try:
            data_url = (info or {}).get("data_url", "")
            if not data_url.startswith("data:") or ";base64," not in data_url:
                continue
            header, b64 = data_url.split(",", 1)
            raw = base64.b64decode(b64)
            if len(raw) > 8_000_000:
                continue
            mime = header[5:].split(";")[0]
            digest = hashlib.sha1(raw).hexdigest()[:16]
            if mime.startswith("image/"):
                from PIL import Image
                img = Image.open(io.BytesIO(raw)).convert("RGB")
                name = f"{digest}.jpg"
                img.save(folder / name, "JPEG", quality=90)
            elif mime.startswith("audio/"):
                ext = ".mp3" if "mpeg" in mime or "mp3" in mime else (Path(str(old_url)).suffix or ".mp3")
                name = f"{digest}{ext}"
                (folder / name).write_bytes(raw)
            else:
                continue
            mapping[old_url] = f"/outputs/users/{safe_owner(owner)}/restored/{name}"
        except Exception:
            continue
    return mapping


def _replace_urls(obj, mapping):
    if isinstance(obj, str):
        return mapping.get(obj, obj)
    if isinstance(obj, dict):
        return {k: _replace_urls(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_replace_urls(v, mapping) for v in obj]
    return obj


@app.post("/api/cloud/import")
def cloud_import(payload: dict, request: Request):
    user = current_user(request)
    owner = user["id"]
    if payload.get("app") not in ("text-to-code-video-studio", None) and "characters" not in payload:
        raise HTTPException(400, "That doesn't look like a Text→Video Studio backup.")
    mapping = _materialize_assets(owner, payload.get("assets") or {})
    counts = {}
    data = store.load()
    for coll, key in (("characters", "name"), ("styles", "name"), ("projects", "name")):
        restored = []
        for raw in payload.get(coll) or []:
            item = _replace_urls(dict(raw), mapping)
            # reuse THIS account's existing item with same name; clone anything
            # belonging to guest/another account so shared presets stay untouched
            existing = next((x for x in data[coll]
                             if (x.get("owner_id") or "guest") == owner
                             and str(x.get(key, "")).lower() == str(item.get(key, "")).lower() and item.get(key)), None)
            if existing:
                item["id"] = existing["id"]
            elif item.get("id"):
                old = store.find(coll, item["id"])
                if old and (old.get("owner_id") or "guest") != owner:
                    item.pop("id", None)
            item["owner_id"] = owner
            restored.append(store.upsert(coll, item))
            data = store.load()
        counts[coll] = len(restored)
    autosave = payload.get("autosave") or {}
    if autosave.get("draft"):
        store.set_autosave(owner, _replace_urls(autosave["draft"], mapping), autosave.get("updated_at", ""))
    return {"ok": True, "restored": counts, "assets_restored": len(mapping)}


@app.post("/api/breakdown")
def api_breakdown(req: BreakdownReq):
    out = bd.breakdown(req.text, req.format, req.provider, req.api_key, req.model)
    total = round(sum(float(s.get("duration") or 0) for s in out["scenes"]), 1)
    out["estimated_duration_sec"] = total
    out["estimated_render_min"] = f"{max(1, round(total/60*1.5))}-{max(2, round(total/60*4))} min (draft, typical laptop)"
    out["characters_detected"] = sorted({s.get("character", "Narrator") for s in out["scenes"]})
    return out


# ---------------------------------------------------------------- characters
@app.post("/api/characters")
def save_character(item: dict, request: Request):
    owner = current_user(request)["id"]
    if item.get("id"):
        ensure_can_touch("characters", item["id"], owner)
    item["owner_id"] = owner
    if not item.get("voice"):
        s = voice_mod.suggest_voice(item.get("description", ""), item.get("gender", ""), item.get("language", "en-IN"))
        item.update({"voice": s["voice"], "rate": s["rate"], "pitch": s["pitch"]})
    return store.upsert("characters", item)


@app.delete("/api/characters/{item_id}")
def delete_character(item_id: str, request: Request):
    ensure_can_touch("characters", item_id, current_user(request)["id"])
    store.delete("characters", item_id)
    return {"ok": True}


@app.post("/api/characters/suggest")
def suggest(item: dict):
    return voice_mod.suggest_voice(item.get("description", ""), item.get("gender", ""), item.get("language", "en-IN"))


@app.post("/api/characters/preview")
def preview_voice(item: dict):
    name = (item.get("name") or "character").strip() or "character"
    text = item.get("text") or f"Hello, I am {name}. This is how I will sound in your video."
    fname = f"preview-{uuid.uuid4().hex[:8]}.mp3"
    ok = voice_mod.synthesize(text, item.get("voice") or "en-IN-PrabhatNeural",
                              item.get("rate") or "+0%", item.get("pitch") or "+0Hz", OUT / "previews" / fname)
    if not ok:
        raise HTTPException(503, "Free voice service unreachable right now (needs internet). Settings are saved and will be used at render time.")
    return {"url": f"/outputs/previews/{fname}"}


@app.post("/api/characters/avatar/generate")
def generate_avatar(item: dict, request: Request):
    name = (item.get("name") or "Character").strip()
    try:
        got = images_mod.avatar_image(name, item.get("description", ""), item.get("prompt", ""),
                                      seed=item.get("seed"), force=bool(item.get("force")))
    except Exception as e:
        raise HTTPException(502, f"Free image AI failed: {e}")
    if item.get("id"):
        ensure_can_touch("characters", item["id"], current_user(request)["id"])
        store.upsert("characters", {"id": item["id"], "avatar_url": got["url"]})
    return got


@app.post("/api/characters/avatar/upload")
async def upload_avatar(request: Request, character_id: str = Form(""), image: UploadFile = File(...)):
    owner = current_user(request)["id"]
    raw = await image.read()
    folder = user_dir(owner) / "avatars"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"upload-{uuid.uuid4().hex[:8]}.jpg"
    try:
        from PIL import Image
        import io as _io
        Image.open(_io.BytesIO(raw)).convert("RGB").save(path, quality=90)
    except Exception as e:
        raise HTTPException(400, f"Could not read that image: {e}")
    url = f"/outputs/users/{safe_owner(owner)}/avatars/{path.name}"
    if character_id:
        ensure_can_touch("characters", character_id, owner)
        store.upsert("characters", {"id": character_id, "avatar_url": url})
    return {"url": url}


# --------------------------------------------------------------------- styles
@app.post("/api/styles")
def save_style(item: dict, request: Request):
    owner = current_user(request)["id"]
    if item.get("id"):
        ensure_can_touch("styles", item["id"], owner)
    item["owner_id"] = owner
    if item.get("prompt") and not item.get("bg"):
        item.update(style_engine.palette_from_prompt(item["prompt"]))
    return store.upsert("styles", item)


@app.delete("/api/styles/{item_id}")
def delete_style(item_id: str, request: Request):
    ensure_can_touch("styles", item_id, current_user(request)["id"])
    store.delete("styles", item_id)
    return {"ok": True}


@app.post("/api/styles/from-prompt")
def style_from_prompt(item: dict):
    return style_engine.palette_from_prompt(item.get("prompt", ""))


@app.post("/api/styles/from-image")
async def style_from_image(request: Request, name: str = Form("Image Style"), prompt: str = Form(""), image: UploadFile = File(...)):
    raw = await image.read()
    try:
        pal = style_engine.palette_from_image(raw)
    except Exception as e:
        raise HTTPException(400, f"Could not read that image: {e}")
    return store.upsert("styles", {"owner_id": current_user(request)["id"], "name": name,
                                    "prompt": prompt or "from reference image", "font_style": "bold", **pal})


# ---------------------------------------------------------------- AI images
@app.post("/api/scene-image")
def scene_image(item: dict):
    prompt = (item.get("prompt") or "").strip()
    if not prompt:
        raise HTTPException(400, "Give this scene a visual prompt first.")
    try:
        return images_mod.scene_image(prompt, item.get("format", "16:9"), seed=item.get("seed"),
                                      style_prompt=item.get("style_prompt", ""), force=bool(item.get("force")))
    except Exception as e:
        raise HTTPException(502, f"Free image AI failed (try again): {e}")


# --------------------------------------------------------------------- music
@app.post("/api/music/builtin")
def builtin_music(item: dict):
    mood = (item.get("mood") or "cinematic").lower()
    path = music_mod.generate_builtin(mood)
    return {"url": f"/outputs/music/{path.name}", "mood": mood}


@app.post("/api/music/upload")
async def upload_music(request: Request, file: UploadFile = File(...)):
    owner = current_user(request)["id"]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", file.filename or "music.mp3")
    if Path(name).suffix.lower() not in (".mp3", ".wav", ".ogg", ".m4a"):
        raise HTTPException(400, "Upload an mp3/wav/ogg/m4a music file.")
    folder = user_dir(owner) / "music"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(await file.read())
    return {"name": name, "url": f"/outputs/users/{safe_owner(owner)}/music/{name}"}


# ------------------------------------------------------------------ code/video
@app.post("/api/codegen")
def api_codegen(req: RenderReq):
    return {"code": codegen.generate_code(req.title, req.scenes, req.style, req.characters, req.format, req.quality, _opts(req))}


@app.post("/api/render")
def api_render(req: RenderReq, request: Request):
    if not req.scenes:
        raise HTTPException(400, "Add at least one scene first (Step 1 -> AI Breakdown).")
    owner = current_user(request)["id"]
    job_id = uuid.uuid4().hex[:10]
    fname = f"video-{job_id}.mp4"
    out_dir = user_dir(owner)
    rel = f"/outputs/users/{safe_owner(owner)}/{fname}"
    JOBS[job_id] = {"id": job_id, "type": "single", "owner_id": owner, "title": req.title,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "status": "queued",
                    "progress": 0, "message": "Queued", "output": None}
    _persist_job(JOBS[job_id])

    def run():
        from core.renderer import render_video
        try:
            job_update(job_id, status="running")
            info = render_video(req.title, req.scenes, req.style, req.characters, req.format, req.quality,
                                out_dir / fname, progress=lambda p, m: job_update(job_id, progress=round(p, 1), message=m),
                                **_opts(req))
            job_update(job_id, status="done", progress=100, message="Done", output=rel,
                       poster=rel.rsplit(".", 1)[0] + ".jpg", **info)
        except Exception as e:
            job_update(job_id, status="error", message=str(e)[:600])

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id}


# ---------------------------------------------------------------------- bulk
@app.post("/api/bulk/plan")
def api_bulk_plan(req: BulkPlanReq):
    if not req.topic.strip():
        raise HTTPException(400, "Give me a topic first.")
    return bulk_mod.bulk_plan(req.topic, max(1, min(req.count, 20)), req.provider, req.api_key, req.model)


@app.post("/api/bulk/render")
def api_bulk_render(req: BulkRenderReq, request: Request):
    items = [it for it in (req.items or []) if it.get("include", True) and it.get("scenes")]
    if not items:
        raise HTTPException(400, "No shorts selected. Generate a bulk plan first and tick at least one.")
    owner = current_user(request)["id"]
    out_dir = user_dir(owner)
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = {"id": job_id, "type": "bulk", "owner_id": owner, "status": "queued", "progress": 0,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "message": "Queued",
                    "results": [], "zip": None, "total": len(items)}
    _persist_job(JOBS[job_id])

    def run():
        from core.renderer import render_video
        job_update(job_id, status="running")
        done_files = []
        for n, it in enumerate(items):
            slug = re.sub(r"[^A-Za-z0-9]+", "-", it.get("title", f"short-{n+1}")).strip("-")[:40] or f"short-{n+1}"
            fname = f"short-{job_id}-{n+1:02d}-{slug}.mp4"
            rel = f"/outputs/users/{safe_owner(owner)}/{fname}"

            def prog(p, m, n=n):
                job_update(job_id, progress=round(((n + p / 100) / len(items)) * 100, 1),
                           message=f"[{n+1}/{len(items)}] {m}")
            try:
                info = render_video(it.get("title", ""), it["scenes"], req.style, req.characters,
                                    "9:16", req.quality, out_dir / fname, progress=prog, **_opts(req))
                results = list(JOBS[job_id].get("results") or []) + [
                    {"title": it.get("title"), "angle": it.get("angle"), "status": "done",
                     "output": rel, "poster": rel.rsplit(".", 1)[0] + ".jpg", **info}]
                job_update(job_id, results=results)
                done_files.append(out_dir / fname)
            except Exception as e:
                results = list(JOBS[job_id].get("results") or []) + [
                    {"title": it.get("title"), "angle": it.get("angle"), "status": "error", "message": str(e)[:300]}]
                job_update(job_id, results=results)
        if done_files:
            zname = f"bulk-{job_id}.zip"
            with zipfile.ZipFile(out_dir / zname, "w", zipfile.ZIP_DEFLATED) as z:
                for f in done_files:
                    z.write(f, f.name)
            job_update(job_id, status="done", progress=100,
                       message=f"Done: {len(done_files)}/{len(items)} shorts rendered",
                       zip=f"/outputs/users/{safe_owner(owner)}/{zname}")
        else:
            job_update(job_id, status="error", message="All shorts failed — see results.")

    threading.Thread(target=run, daemon=True).start()
    return {"job_id": job_id, "count": len(items)}


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found")
    return JOBS[job_id]


@app.post("/api/projects")
def save_project(item: dict, request: Request):
    owner = current_user(request)["id"]
    if item.get("id"):
        ensure_can_touch("projects", item["id"], owner)
    item["owner_id"] = owner
    return store.upsert("projects", item)


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(BASE / "static" / "sw.js", media_type="application/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(BASE / "static" / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/outputs", StaticFiles(directory=str(OUT)), name="outputs")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
