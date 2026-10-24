"""
Animated video renderer v2.

- Pillow draws every frame -> bundled FFmpeg encodes MP4.
- Voice per character via free Edge-TTS, karaoke word-highlight synced to speech.
- NEW: free AI scene images (Pollinations) as Ken-Burns animated backgrounds.
- NEW: character avatars on screen, pulsing / bobbing while they speak.
- NEW: background music (built-in synthesized moods or your upload) with
  auto-ducking under voices.
- 16:9 (YouTube) and 9:16 (Shorts/Reels), draft + full quality.
"""
import hashlib, math, re, subprocess, tempfile, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from . import voices as voice_mod
from . import images as images_mod
from . import music as music_mod

ROOT = Path(__file__).resolve().parent.parent
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts", "C:/Windows/Fonts", "/System/Library/Fonts"]
_font_cache = {}


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _font_path(bold):
    names = ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Helvetica.ttc"] if bold else ["DejaVuSans.ttf", "arial.ttf", "Helvetica.ttc"]
    for d in FONT_DIRS:
        for n in names:
            p = Path(d) / n
            if p.exists():
                return str(p)
    return None


def font(size, bold=True):
    key = (int(size), bold)
    if key not in _font_cache:
        path = _font_path(bold)
        _font_cache[key] = ImageFont.truetype(path, int(size)) if path else ImageFont.load_default()
    return _font_cache[key]


def hex_rgb(h, default=(124, 58, 237)):
    try:
        h = str(h).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def blend(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def ease(t):
    return 1 - (1 - max(0.0, min(1.0, t))) ** 3


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in str(text).split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur); cur = word
    if cur:
        lines.append(cur)
    return lines


def make_background(W, H, bg, primary, seed=0):
    top, bottom = np.array(bg, float), np.array(blend(bg, primary, 0.45), float)
    grad = np.linspace(0, 1, H)[:, None, None]
    arr = (top[None, None, :] * (1 - grad) + bottom[None, None, :] * grad)
    arr = np.repeat(arr, W, axis=1).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    rng = (seed * 37) % 200
    gd.ellipse([W * 0.62 - rng, -H * 0.25, W * 1.25, H * 0.45], fill=tuple(int(c * 0.55) for c in primary))
    gd.ellipse([-W * 0.2, H * 0.65, W * 0.35 + rng, H * 1.25], fill=tuple(int(c * 0.30) for c in primary))
    img = Image.blend(img, Image.blend(img, glow.filter(ImageFilter.GaussianBlur(90)), 0.9), 0.55)
    d = ImageDraw.Draw(img, "RGBA")
    step = max(36, W // 28)
    for x in range(step, W, step):
        for y in range(step, H, step):
            d.ellipse([x, y, x + 3, y + 3], fill=(255, 255, 255, 22))
    return img


# ------------------------------------------------------------ AI backgrounds
def _cover_scaled(path, W, H, bg, scale=1.16):
    """Load image, cover-crop to (W*scale, H*scale), darkened for text readability."""
    img = Image.open(path).convert("RGB")
    tw, th = int(W * scale), int(H * scale)
    img = ImageOps.fit(img, (tw, th), Image.BILINEAR)
    return Image.blend(img, Image.new("RGB", (tw, th), bg), 0.42)


def _ken_burns(scaled, W, H, p, idx):
    """Animated crop: zoom-in / zoom-out / pan depending on scene index."""
    sw, sh = scaled.size
    mode = idx % 4
    if mode == 0:      # zoom in
        cw = sw * (1 - 0.12 * p); cx, cy = sw * 0.5, sh * 0.5
    elif mode == 1:    # zoom out
        cw = sw * (0.88 + 0.12 * p); cx, cy = sw * 0.5, sh * 0.5
    elif mode == 2:    # pan right + slight zoom
        cw = sw * 0.92; cx = sw * (0.46 + 0.08 * p); cy = sh * 0.5
    else:              # pan up + slight zoom
        cw = sw * 0.92; cx = sw * 0.5; cy = sh * (0.54 - 0.08 * p)
    ch = cw * H / W
    if ch > sh:
        ch = sh * 0.98; cw = ch * W / H
    x0 = max(0, min(sw - cw, cx - cw / 2)); y0 = max(0, min(sh - ch, cy - ch / 2))
    return scaled.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.BILINEAR)


def _circle_avatar(path, size):
    img = Image.open(path).convert("RGB")
    img = ImageOps.fit(img, (size, size), Image.BILINEAR)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size * 4, size * 4], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask.resize((size, size), Image.BILINEAR))
    return out


# --------------------------------------------------------------------- audio
def _to_wav(src: Path, dst: Path):
    subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(src), "-ar", "44100", "-ac", "1", str(dst)],
                   check=True, timeout=180)


def _wav_duration(p: Path):
    with wave.open(str(p)) as w:
        return w.getnframes() / float(w.getframerate())


def _silence_wav(p: Path, seconds: float):
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(44100)
        w.writeframes(b"\x00\x00" * int(44100 * seconds))


def _char_map(characters):
    m = {}
    for c in characters or []:
        if c.get("name"):
            m[c["name"].strip().lower()] = c
    return m


def _resolve_character(name, cmap):
    key = (name or "Narrator").strip().lower()
    if key in cmap:
        return cmap[key]
    h = int(hashlib.md5(key.encode()).hexdigest(), 16)
    sugg = voice_mod.suggest_voice(name or "", "", "en-IN")
    return {"name": name or "Narrator", "voice": sugg["voice"],
            "rate": sugg["rate"], "pitch": f"{(h % 41) - 20:+d}Hz", "color": "#f59e0b"}


def prepare_audio(scenes, characters, work: Path, progress):
    cmap = _char_map(characters)
    wavs, durations = [], []
    gap = 0.35
    for i, sc in enumerate(scenes):
        progress(2 + 18 * (i / max(1, len(scenes))), f"Voice {i+1}/{len(scenes)}: {sc.get('character','Narrator')}")
        ch = _resolve_character(sc.get("character"), cmap)
        mp3, wv = work / f"s{i}.mp3", work / f"s{i}.wav"
        ok = voice_mod.synthesize(sc.get("text", ""), ch.get("voice"), ch.get("rate"), ch.get("pitch"), mp3)
        if ok:
            try:
                _to_wav(mp3, wv)
            except Exception:
                ok = False
        if not ok:
            _silence_wav(wv, float(sc.get("duration") or max(3.0, len(str(sc.get('text','')).split()) / 2.4)))
        dur = _wav_duration(wv)
        wavs.append(wv); durations.append(dur + gap)

    concat = work / "audio.wav"
    with wave.open(str(concat), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(44100)
        sil = b"\x00\x00" * int(44100 * gap)
        for wv in wavs:
            with wave.open(str(wv)) as w:
                out.writeframes(w.readframes(w.getnframes()))
            out.writeframes(sil)
    return concat, durations


def _prepare_music(music_cfg, voice_wav, work: Path, progress):
    """Return mixed (voice+ducked music) wav path, or the plain voice wav."""
    if not music_cfg or not music_cfg.get("enabled", True):
        return voice_wav
    source = str(music_cfg.get("source") or "none")
    if source in ("none", ""):
        return voice_wav
    try:
        progress(32, "Preparing background music + auto-ducking…")
        if source.startswith("builtin:"):
            music_wav = music_mod.generate_builtin(source.split(":", 1)[1])
        else:
            src = images_mod.resolve(source) or (ROOT / "outputs" / "music" / Path(source).name)
            if not Path(src).exists():
                return voice_wav
            if str(src).lower().endswith(".wav"):
                music_wav = Path(src)
            else:
                music_wav = work / "music.wav"; _to_wav(Path(src), music_wav)
        vol = float(music_cfg.get("volume", 35)); vol = vol / 100 if vol > 1 else vol
        duck = float(music_cfg.get("duck", 80)); duck = duck / 100 if duck > 1 else duck
        return music_mod.mix_with_ducking(voice_wav, music_wav, work / "mixed.wav",
                                          volume=max(0.0, min(1.0, vol)), duck=max(0.0, min(0.97, duck)))
    except Exception:
        return voice_wav  # music must never kill a render


# --------------------------------------------------------------------- frames
RES = {("16:9", "draft"): (1280, 720), ("16:9", "full"): (1920, 1080),
       ("9:16", "draft"): (720, 1280), ("9:16", "full"): (1080, 1920)}


def draw_scene(base, sc, ch, style_cols, W, H, S, t_in_scene, dur, idx, total, overall_p, title_text,
               avatar=None, has_image=False):
    img = base.copy()
    d = ImageDraw.Draw(img, "RGBA")
    bg, primary, accent, text_c = style_cols
    p = max(0.0, min(1.0, t_in_scene / max(dur, 0.01)))
    ent = ease(t_in_scene / 0.6)
    anim = sc.get("animation") or "fade_up"
    x_off = (1 - ent) * 90 * S if anim == "slide_left" else 0
    y_off = (1 - ent) * 44 * S if anim in ("fade_up", "pop", "zoom_focus") else 0
    fade = ent if anim == "fade_up" else 1.0
    mx = int(64 * S) if W > H else int(44 * S)

    if has_image:  # soft dark shade behind text zone
        d.rectangle([0, 0, W, int(H * 0.74)], fill=(0, 0, 0, 58))

    # header: character chip (real avatar if available) + scene counter
    ch_name = str(sc.get("character") or "Narrator")
    ch_col = hex_rgb((ch or {}).get("color") or "#7c3aed")
    cy, r = int(52 * S), int(26 * S)
    if avatar:
        img.paste(avatar["small"], (mx, cy - r), avatar["small"])
        d.ellipse([mx, cy - r, mx + 2 * r, cy + r], outline=ch_col + (255,), width=max(2, int(3 * S)))
    else:
        d.ellipse([mx, cy - r, mx + 2 * r, cy + r], fill=ch_col)
        initials = "".join(w[0] for w in ch_name.split()[:2]).upper() or "N"
        f_init = font(24 * S)
        iw = d.textlength(initials, font=f_init)
        d.text((mx + r - iw / 2, cy - 15 * S), initials, font=f_init, fill=(255, 255, 255))
    d.text((mx + 2 * r + 14 * S, cy - 16 * S), ch_name, font=font(27 * S), fill=text_c)
    counter = f"{idx+1:02d} / {total:02d}"
    f_c = font(24 * S, bold=False)
    d.text((W - mx - d.textlength(counter, font=f_c), cy - 14 * S), counter, font=f_c, fill=blend(text_c, bg, 0.35))
    if title_text:
        d.text((mx, cy + r + 12 * S), str(title_text)[:42].upper(), font=font(19 * S, bold=False), fill=blend(accent, bg, 0.1))

    # scene title
    y = int(H * (0.20 if W > H else 0.16)) + y_off
    f_title = font((54 if W > H else 46) * S * (1.06 - 0.06 * ent if anim == "zoom_focus" else 1))
    for line in wrap(d, sc.get("title") or "", f_title, W - 2 * mx)[:2]:
        d.text((mx + x_off, y), line, font=f_title, fill=blend(text_c, bg, 1 - fade))
        y += int(64 * S)
    d.rounded_rectangle([mx + x_off, y + 6 * S, mx + x_off + 110 * S * ent, y + 14 * S], radius=4, fill=accent)
    y += int(46 * S)

    # body text with karaoke highlight / typewriter
    body = str(sc.get("text") or "")
    f_body = font((39 if W > H else 35) * S, bold=False)
    space_w = d.textlength(" ", font=f_body)
    line_h = int(56 * S) if W > H else int(52 * S)
    body_w = W - 2 * mx - (int(240 * S) if (avatar and W > H) else 0)
    if anim == "typewriter":
        shown = body[: int(len(body) * min(1.0, p / 0.8))]
        for line in wrap(d, shown, f_body, body_w)[:7]:
            d.text((mx, y), line, font=f_body, fill=text_c); y += line_h
        if p < 0.82:
            d.rectangle([mx, y + 6 * S, mx + 18 * S, y + 12 * S], fill=accent)
    else:
        words = body.split()
        cur = int(p * max(1, len(words)))
        lines_words, cur_line, cur_w = [], [], 0.0
        for wi, w in enumerate(words):
            ww = d.textlength(w, font=f_body)
            if cur_line and cur_w + ww > body_w:
                lines_words.append(cur_line); cur_line, cur_w = [], 0.0
            cur_line.append((wi, w, ww)); cur_w += ww + space_w
        if cur_line: lines_words.append(cur_line)
        for line in lines_words[:7]:
            x = mx + x_off
            for wi, w, ww in line:
                col = accent if wi == cur else (text_c if wi < cur else blend(text_c, bg, 0.45))
                if wi == cur:
                    d.rounded_rectangle([x - 5 * S, y + 4 * S, x + ww + 5 * S, y + line_h - 8 * S], radius=8, fill=blend(accent, bg, 0.65))
                d.text((x, y + y_off * 0.4), w, font=f_body, fill=col); x += ww + space_w
            y += line_h

    # chart bars OR keyword pills
    if anim == "chart_bars":
        nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", body)][:5]
        vals = nums or [40, 70, 55, 90, 65]
        vals = [v / max(vals) for v in vals]
        bw, base_y, max_h = int(64 * S), int(H - 190 * S), int(150 * S)
        x = mx
        for v in vals:
            bh = max_h * v * ease(min(1.0, p / 0.7))
            d.rounded_rectangle([x, base_y - bh, x + bw, base_y], radius=10, fill=accent)
            x += bw + int(28 * S)
    else:
        y_pill = int(H - 150 * S); x = mx
        f_k = font(22 * S, bold=False)
        for kw in (sc.get("keywords") or [])[:4]:
            kw = str(kw)[:18]
            kw_w = d.textlength(kw, font=f_k) + 32 * S
            if x + kw_w > W - mx - (int(250 * S) if avatar else 0): break
            d.rounded_rectangle([x, y_pill, x + kw_w, y_pill + 42 * S], radius=21, fill=blend(primary, bg, 0.25))
            d.text((x + 16 * S, y_pill + 8 * S), kw, font=f_k, fill=text_c)
            x += kw_w + 12 * S

    # big speaking avatar (bottom-right): bob + pulsing rings while speaking
    if avatar:
        big = avatar["big"]; D = big.width
        bob = int(math.sin(t_in_scene * 2 * math.pi * 0.8) * 5 * S)
        ax, ay = W - mx - D, int(H - D - 120 * S) + bob
        if p < 0.96:
            for k in range(3):
                ph = (t_in_scene * 0.65 + k / 3) % 1.0
                rr = D / 2 + ph * 22 * S
                d.ellipse([ax + D / 2 - rr, ay + D / 2 - rr, ax + D / 2 + rr, ay + D / 2 + rr],
                          outline=accent + (int((1 - ph) * 150),), width=max(2, int(3 * S)))
        img.paste(big, (ax, ay), big)
        d.ellipse([ax, ay, ax + D, ay + D], outline=ch_col + (255,), width=max(2, int(4 * S)))
        f_tag = font(20 * S)
        tw = d.textlength(ch_name, font=f_tag)
        tx = ax + D / 2 - tw / 2 - 12 * S
        d.rounded_rectangle([tx, ay + D + 8 * S, tx + tw + 24 * S, ay + D + 42 * S], radius=16, fill=ch_col)
        d.text((tx + 12 * S, ay + D + 14 * S), ch_name, font=f_tag, fill=(255, 255, 255))

    # overall progress bar
    bh = max(6, int(8 * S))
    d.rectangle([0, H - bh, W, H], fill=blend(primary, bg, 0.6))
    d.rectangle([0, H - bh, int(W * overall_p), H], fill=accent)

    left = dur - t_in_scene
    if left < 0.3:
        img = Image.blend(img, Image.new("RGB", (W, H), bg), (0.3 - left) / 0.3 * 0.55)
    return img


def render_video(title, scenes, style, characters, fmt="16:9", quality="draft",
                 out_path=Path("outputs/video.mp4"), progress=lambda p, m: None, fps=24, voice=True,
                 use_images=True, generate_images=False, show_avatars=True, music=None):
    if not scenes:
        raise ValueError("No scenes to render")
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    W, H = RES.get((fmt, quality), (1280, 720))
    S = (W / 1280) if W >= H else (W / 720)
    style = style or {}
    cols = (hex_rgb(style.get("bg"), (11, 16, 32)), hex_rgb(style.get("primary")),
            hex_rgb(style.get("accent"), (245, 158, 11)), hex_rgb(style.get("text"), (255, 255, 255)))
    cmap = _char_map(characters)

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        if voice:
            audio, durations = prepare_audio(scenes, characters, work, progress)
        else:
            durations = [float(s.get("duration") or 5) for s in scenes]
            audio = work / "audio.wav"; _silence_wav(audio, sum(durations))
        audio = _prepare_music(music, audio, work, progress)
        total_dur = sum(durations)

        # scene AI backgrounds (pre-generated in UI, or generated now if asked)
        scaled_imgs = []
        for i, sc in enumerate(scenes):
            simg = None
            if use_images:
                path = images_mod.resolve(sc.get("image_url") or sc.get("image"))
                if path is None and generate_images:
                    progress(22 + 8 * (i / max(1, len(scenes))), f"🎨 AI image {i+1}/{len(scenes)}: {sc.get('title','')}")
                    try:
                        got = images_mod.scene_image(sc.get("visual_prompt") or sc.get("title") or sc.get("text", ""),
                                                     fmt, seed=1000 + i * 17, style_prompt=style.get("prompt", ""))
                        sc["image_url"] = got["url"]; path = Path(got["path"])
                    except Exception:
                        path = None
                if path is not None:
                    try:
                        simg = _cover_scaled(path, W, H, cols[0])
                    except Exception:
                        simg = None
            scaled_imgs.append(simg)

        # avatars
        avatars = {}
        if show_avatars:
            big_size = int((225 if W >= H else 190) * S)
            for key, c in cmap.items():
                pth = images_mod.resolve(c.get("avatar_url"))
                if pth:
                    try:
                        avatars[key] = {"big": _circle_avatar(pth, big_size),
                                        "small": _circle_avatar(pth, int(52 * S))}
                    except Exception:
                        pass

        bases = [make_background(W, H, cols[0], cols[1], seed=i) if scaled_imgs[i] is None else None
                 for i in range(len(scenes))]

        cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
               "-i", str(audio), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest",
               "-movflags", "+faststart", str(out_path)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            elapsed = 0.0
            for i, sc in enumerate(scenes):
                ch = _resolve_character(sc.get("character"), cmap)
                av = avatars.get((sc.get("character") or "Narrator").strip().lower())
                n = max(1, int(durations[i] * fps))
                progress(35 + 62 * (elapsed / total_dur), f"Animating scene {i+1}/{len(scenes)}: {sc.get('title','')}")
                for f in range(n):
                    t = f / fps
                    base = _ken_burns(scaled_imgs[i], W, H, t / max(durations[i], 0.01), i) if scaled_imgs[i] is not None else bases[i]
                    frame = draw_scene(base, sc, ch, cols, W, H, S, t, durations[i], i, len(scenes),
                                       (elapsed + t) / total_dur, title, avatar=av,
                                       has_image=scaled_imgs[i] is not None)
                    if i == 0 and f == int(fps * 0.8):
                        frame.save(str(out_path.with_suffix(".jpg")), quality=88)
                    proc.stdin.write(frame.tobytes())
                elapsed += durations[i]
            proc.stdin.close()
            err = proc.stderr.read().decode(errors="ignore")
            proc.wait(timeout=3600)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg failed: {err[-1500:]}")
        except Exception:
            try: proc.kill()
            except Exception: pass
            raise
    progress(100, "Done")
    return {"output": str(out_path), "duration": round(total_dur, 1), "resolution": f"{W}x{H}",
            "scenes": len(scenes), "images_used": sum(1 for x in scaled_imgs if x is not None),
            "avatars_used": len(avatars)}
