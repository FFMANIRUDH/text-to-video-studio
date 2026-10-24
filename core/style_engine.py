"""Custom style engine: style prompt / reference image -> colour palette + look."""
import io, colorsys
from PIL import Image

PALETTES = [
    (["dark", "cinematic", "movie", "film"],       {"bg": "#0b1020", "primary": "#7c3aed", "accent": "#f59e0b", "text": "#ffffff"}),
    (["neon", "cyberpunk", "tech", "futuristic"],  {"bg": "#050510", "primary": "#06b6d4", "accent": "#ec4899", "text": "#e0faff"}),
    (["minimal", "clean", "white", "simple"],      {"bg": "#f8fafc", "primary": "#0f172a", "accent": "#2563eb", "text": "#0f172a"}),
    (["kids", "cartoon", "fun", "playful", "bright"], {"bg": "#fef9c3", "primary": "#ea580c", "accent": "#2563eb", "text": "#1e293b"}),
    (["sunset", "warm", "story", "orange"],        {"bg": "#2b1608", "primary": "#ea580c", "accent": "#facc15", "text": "#fff7ed"}),
    (["nature", "forest", "green", "earth"],       {"bg": "#0a1f14", "primary": "#16a34a", "accent": "#a3e635", "text": "#f0fdf4"}),
    (["ocean", "sea", "blue", "water"],            {"bg": "#041e33", "primary": "#0284c7", "accent": "#22d3ee", "text": "#f0f9ff"}),
    (["royal", "luxury", "gold", "king"],          {"bg": "#170f2e", "primary": "#9333ea", "accent": "#eab308", "text": "#fefce8"}),
    (["horror", "scary", "dark red"],              {"bg": "#120404", "primary": "#991b1b", "accent": "#ef4444", "text": "#fee2e2"}),
    (["pastel", "soft", "cute", "pink"],           {"bg": "#fdf2f8", "primary": "#db2777", "accent": "#8b5cf6", "text": "#500724"}),
]
DEFAULT = {"bg": "#0b1020", "primary": "#7c3aed", "accent": "#f59e0b", "text": "#ffffff"}


def palette_from_prompt(prompt: str):
    p = (prompt or "").lower()
    for keys, pal in PALETTES:
        if any(k in p for k in keys):
            return dict(pal)
    return dict(DEFAULT)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def palette_from_image(image_bytes: bytes):
    """Extract dominant colours from a reference image and build a readable palette."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((160, 160))
    q = img.quantize(colors=8, method=Image.MEDIANCUT)
    palette = q.getpalette()[: 8 * 3]
    counts = sorted(q.getcolors() or [], reverse=True)
    cols = []
    for count, idx in counts:
        rgb = tuple(palette[idx * 3: idx * 3 + 3])
        cols.append((count, rgb))
    if not cols:
        return dict(DEFAULT)

    def lum(rgb): return 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    def sat(rgb):
        h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
        return s

    darkest = min(cols, key=lambda c: lum(c[1]))[1]
    most_sat = max(cols, key=lambda c: sat(c[1]) * (c[0] ** 0.3))[1]
    others = [c[1] for c in cols if c[1] not in (darkest, most_sat)]
    accent = max(others, key=lambda c: sat(c)) if others else most_sat
    bg = darkest if lum(darkest) < 140 else tuple(int(c * 0.35) for c in darkest)
    return {"bg": _hex(bg), "primary": _hex(most_sat), "accent": _hex(accent), "text": "#ffffff",
            "extracted": [_hex(c[1]) for c in cols[:6]]}
