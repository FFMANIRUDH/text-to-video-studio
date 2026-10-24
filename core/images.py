"""
Free AI images via Pollinations (no API key, no signup).
Scene backgrounds + character avatars, cached on disk so each image
is only generated once.
"""
import hashlib, threading, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs"

# The free anonymous Pollinations tier rate-limits bursty traffic (HTTP 402/429).
# Serialize image requests server-wide and pace them, with backoff retries.
_gate = threading.Lock()
_last_req = [0.0]
MIN_INTERVAL = 6.0


def _seed_for(text):
    return int(hashlib.md5(str(text).encode()).hexdigest(), 16) % 999999


def _fetch(prompt, w, h, subdir, seed=None, force=False):
    import requests
    from PIL import Image
    import io

    seed = seed if seed is not None else _seed_for(prompt)
    key = hashlib.sha1(f"{prompt}|{w}x{h}|{seed}".encode()).hexdigest()[:16]
    folder = OUT / subdir
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}.jpg"
    url = f"/outputs/{subdir}/{key}.jpg"
    if path.exists() and path.stat().st_size > 4000 and not force:
        return {"path": str(path), "url": url, "cached": True, "seed": seed}

    q = urllib.parse.quote(prompt[:900])
    last_err = None
    for attempt in range(3):
        api = (f"https://image.pollinations.ai/prompt/{q}"
               f"?width={w}&height={h}&seed={seed + attempt}&model=sana&nologo=true")
        with _gate:  # one free-tier request at a time, spaced out
            wait = MIN_INTERVAL - (time.time() - _last_req[0])
            if wait > 0:
                time.sleep(wait)
            try:
                r = requests.get(api, timeout=90, headers={"User-Agent": "TextToVideoStudio/1.0"})
                _last_req[0] = time.time()
                if r.status_code == 200 and len(r.content) > 3000:
                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    img.save(path, "JPEG", quality=88)
                    return {"path": str(path), "url": url, "cached": False, "seed": seed + attempt}
                last_err = f"HTTP {r.status_code} (free-tier limit — retrying)"
            except Exception as e:
                _last_req[0] = time.time()
                last_err = str(e)
        if attempt < 2:
            time.sleep(12 * (attempt + 1))  # backoff lets free-tier credits refill
    raise RuntimeError(f"Free image AI is busy right now ({last_err}). Wait ~30 seconds and try again — generated images are cached once done.")


def scene_image(prompt, fmt="16:9", seed=None, style_prompt="", force=False):
    # 768px source (renderer upscales + Ken Burns): much friendlier to the free tier
    w, h = (768, 432) if fmt != "9:16" else (432, 768)
    full = (f"{prompt}. {style_prompt}. cinematic digital illustration, rich detail, "
            f"atmospheric lighting, no text, no words, no watermark, no logo")
    return _fetch(full, w, h, "scene_images", seed, force)


def avatar_image(name, description="", prompt="", seed=None, force=False):
    full = prompt or (f"character portrait of {name}, {description}, head and shoulders portrait, "
                      f"facing camera, expressive face, digital painting, clean simple background, no text, no watermark")
    return _fetch(full, 512, 512, "avatars", seed, force)


def resolve(url_or_path):
    """Map '/outputs/avatars/x.jpg' (web URL) -> real file Path, if it exists."""
    if not url_or_path:
        return None
    s = str(url_or_path)
    candidates = []
    if s.startswith("/outputs/"):
        candidates.append(ROOT / s.lstrip("/"))
    elif s.startswith("outputs/"):
        candidates.append(ROOT / s)
    candidates.append(Path(s))
    for c in candidates:
        if c.exists():
            return c
    return None
