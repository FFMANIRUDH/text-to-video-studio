"""
Free AI breakdown engine.

- Default: fully OFFLINE heuristic engine (no key, no cost) that detects
  topic / prompt / raw text / dialogue script and splits it into scenes,
  assigns characters, visual prompts, animations and durations.
- Optional: plug in a FREE LLM (Groq / Gemini / OpenRouter free models)
  with your own free API key for smarter breakdowns + topic expansion.
"""
import json, re, collections

STOP = set("""a an the is are was were be been being am do does did have has had will would shall should can could may might
i you he she it we they me him her us them my your his its our their to of in on at for with from by as and or but if then than so
that this those these there here what which who whom when where why how all any both each few more most other some such no nor not
only own same too very just about into over under again further once out up down off of""".split())

ANIMATIONS = ["fade_up", "slide_left", "typewriter", "pop", "word_highlight", "chart_bars", "zoom_focus"]


def _keywords(text, n=5):
    words = re.findall(r"[A-Za-z][a-zA-Z\-]{2,}", text.lower())
    freq = collections.Counter(w for w in words if w not in STOP)
    return [w for w, _ in freq.most_common(n)]


def _est_duration(text):
    words = max(1, len(text.split()))
    return round(max(3.0, min(18.0, words / 2.4 + 0.6)), 1)  # ~145 wpm narration


def _pick_animation(text, idx):
    t = text.lower()
    if re.search(r"\d+%|\d+\s*(million|billion|crore|lakh|years|km|kg)", t): return "chart_bars"
    if text.strip().endswith("?"): return "pop"
    if any(w in t for w in ["first", "second", "third", "finally", "step"]): return "slide_left"
    if len(text) < 70: return "typewriter"
    return ["word_highlight", "fade_up", "slide_left", "zoom_focus"][idx % 4]


def _make_scene(idx, text, character="Narrator", title=None):
    kw = _keywords(text)
    return {
        "id": idx + 1,
        "title": title or (" ".join(w.capitalize() for w in kw[:3]) or f"Scene {idx+1}"),
        "text": text.strip(),
        "character": character or "Narrator",
        "visual_prompt": ("cinematic illustration of " + ", ".join(kw)) if kw else "abstract cinematic background",
        "keywords": kw,
        "animation": _pick_animation(text, idx),
        "duration": _est_duration(text),
    }


DIALOGUE_RE = re.compile(r"^\s*(?:\[([A-Za-z][\w .\-]{0,30})\]|([A-Z][A-Za-z][\w .\-]{0,30})\s*[:\-])\s*(.+)$")


def _sentences(text):
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    return [p.strip() for p in parts if p.strip()]


def _expand_topic(topic):
    """Offline topic -> starter script structure (connect a free LLM for a full script)."""
    t = topic.strip().rstrip(".")
    rows = [
        ("The Hook", f"What if everything you thought about {t} was only half the story? Stay with me, because this changes how you see it forever."),
        ("Introduction", f"Today we are exploring {t}. By the end of this video, you will understand what it is, why it matters, and the key ideas most people miss."),
        ("The Background", f"First, let us look at the background of {t}. Understanding where it started makes everything that follows much clearer."),
        ("Key Idea One", f"The first key idea about {t} is the foundation everything else is built on. Once you see it, the rest starts to fall into place."),
        ("Key Idea Two", f"Next comes the part that surprises most people about {t}. This is where the story takes an unexpected turn."),
        ("Why It Matters", f"So why does {t} matter to you, right now? Because its impact reaches further into everyday life than most of us realise."),
        ("Conclusion", f"That is the story of {t}. If this helped you see it in a new way, share it with someone who needs to hear it — and keep asking better questions."),
    ]
    return [_make_scene(i, txt, "Narrator", title) for i, (title, txt) in enumerate(rows)]


def offline_breakdown(raw: str, fmt: str = "16:9"):
    raw = (raw or "").strip()
    if not raw:
        return {"title": "", "scenes": [], "detected_type": "empty", "engine": "offline", "warnings": ["No text provided."]}

    lines = [l for l in raw.splitlines() if l.strip()]
    dialogue = []
    for line in lines:
        m = DIALOGUE_RE.match(line)
        if m and len(line) < 400:
            dialogue.append(((m.group(1) or m.group(2)).strip().title(), m.group(3).strip()))

    words = len(raw.split())

    # 1) Dialogue script  e.g.  RAJ: ...  /  [Queen] ...
    if len(dialogue) >= 2 and len(dialogue) >= len(lines) * 0.5:
        scenes = []
        for i, (char, txt) in enumerate(dialogue):
            for j, s in enumerate(_sentences(txt) or [txt]):
                scenes.append(_make_scene(len(scenes), s, char))
        return {"title": scenes[0]["title"], "scenes": scenes, "detected_type": "dialogue script",
                "engine": "offline", "warnings": []}

    # 2) Short input = topic / prompt
    if words <= 20 and "\n" not in raw:
        scenes = _expand_topic(raw)
        return {"title": raw.title(), "scenes": scenes, "detected_type": "topic",
                "engine": "offline",
                "warnings": ["Short input detected as a TOPIC. Offline engine created a starter script structure — edit the scenes, or add a free Groq/Gemini key in AI Settings for a fully written script."]}

    # 3) Bullet / list input
    bullets = [re.sub(r"^[\-\*\•\d\.\)\s]+", "", l).strip() for l in lines if re.match(r"^\s*([\-\*\•]|\d+[\.\)])\s+", l)]
    if len(bullets) >= 3 and len(bullets) >= len(lines) * 0.6:
        scenes = [_make_scene(i, b) for i, b in enumerate(bullets) if b]
        return {"title": scenes[0]["title"], "scenes": scenes, "detected_type": "list / outline",
                "engine": "offline", "warnings": []}

    # 4) Raw text / script / prompt -> group sentences into ~15-25 word scenes
    target = 14 if fmt == "9:16" else 22
    scenes, buf = [], ""
    for sent in _sentences(raw):
        buf = (buf + " " + sent).strip()
        if len(buf.split()) >= target:
            scenes.append(_make_scene(len(scenes), buf)); buf = ""
    if buf:
        scenes.append(_make_scene(len(scenes), buf))
    first_title = scenes[0]["title"] if scenes else "Untitled"
    return {"title": first_title, "scenes": scenes, "detected_type": "script / raw text",
            "engine": "offline", "warnings": []}


# ---------------------------------------------------------------- free LLMs
SYSTEM = """You are a video scene-breakdown engine. The user may give a topic, prompt, raw text, or full script (possibly with dialogue like NAME: line).
Return ONLY valid JSON, no markdown fences:
{"title": "...", "scenes": [{"title":"short","text":"narration/dialogue for this scene (15-25 words)","character":"Narrator or character name","visual_prompt":"what to show on screen","keywords":["a","b"],"animation":"one of fade_up|slide_left|typewriter|pop|word_highlight|chart_bars|zoom_focus","duration":6}]}
If input is just a topic, WRITE a full engaging script first, then split it. Keep every scene's text speakable in one breath-group. Preserve original character names in dialogue."""


def _parse_llm_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    data = json.loads(text)
    scenes = []
    for i, s in enumerate(data.get("scenes", [])):
        base = _make_scene(i, s.get("text", ""), s.get("character", "Narrator"), s.get("title"))
        base.update({k: s[k] for k in ("visual_prompt", "keywords", "animation", "duration") if s.get(k)})
        if base["animation"] not in ANIMATIONS: base["animation"] = "fade_up"
        scenes.append(base)
    return {"title": data.get("title", ""), "scenes": scenes, "detected_type": "ai breakdown", "engine": "llm", "warnings": []}


def llm_breakdown(raw, provider, api_key, model=""):
    import requests
    provider = (provider or "").lower()
    if provider in ("groq", "openrouter"):
        url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
        model = model or ("llama-3.3-70b-versatile" if provider == "groq" else "meta-llama/llama-3.3-70b-instruct:free")
        r = requests.post(url, timeout=90, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                          json={"model": model, "temperature": 0.6,
                                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": raw[:12000]}]})
        r.raise_for_status()
        return _parse_llm_json(r.json()["choices"][0]["message"]["content"])
    if provider == "gemini":
        model = model or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        r = requests.post(url, timeout=90, json={"contents": [{"parts": [{"text": SYSTEM + "\n\nUSER INPUT:\n" + raw[:12000]}]}]})
        r.raise_for_status()
        return _parse_llm_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    raise ValueError(f"Unknown provider: {provider}")


def breakdown(raw, fmt="16:9", provider="offline", api_key="", model=""):
    if provider and provider != "offline" and api_key:
        try:
            out = llm_breakdown(raw, provider, api_key, model)
            if out["scenes"]:
                return out
            raise ValueError("AI returned no scenes")
        except Exception as e:
            out = offline_breakdown(raw, fmt)
            out["warnings"] = [f"Free AI ({provider}) failed: {e}. Fell back to the offline engine."] + out.get("warnings", [])
            return out
    return offline_breakdown(raw, fmt)
