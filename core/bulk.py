"""
Bulk mode: 1 topic -> N ready-to-render Shorts (default 10).
Offline angle-engine by default; a free LLM key (Groq/Gemini/OpenRouter)
writes much richer, topic-specific scripts when provided.
"""
import json, re
from .breakdown import _make_scene

ANGLES = [
    ("Shocking Fact", "You won't believe this about {t}",
     ["Stop scrolling. Here is the one fact about {t} that changes everything you thought you knew.",
      "Most people get {t} completely wrong, because the real story is far stranger than the version everyone repeats.",
      "Once you understand this hidden side of {t}, you start noticing its effect everywhere around you.",
      "And the wildest part? This is only the beginning of what {t} is really hiding in plain sight.",
      "Follow for part two, because {t} has even bigger secrets waiting for you tomorrow."]),
    ("Myth Busted", "The biggest myth about {t}",
     ["Everything you were told about {t} is wrong. Here is the truth nobody explains properly.",
      "The myth sounds convincing, and that is exactly why millions of people still believe it today.",
      "But when you look closer at how {t} actually works, the myth completely falls apart.",
      "The real explanation is simpler, smarter, and honestly far more interesting than the myth.",
      "Share this with someone who still believes the myth about {t}. They need to see this."]),
    ("How It Works", "How {t} actually works",
     ["You use or see {t} all the time, but do you know how it actually works underneath?",
      "It starts with one simple principle, and everything else about {t} is built on top of it.",
      "Then a chain reaction begins, where each step of {t} quietly triggers the next one.",
      "Put it all together and you get the result everyone notices, but nobody thinks about.",
      "Now you will never look at {t} the same way again. Follow for more breakdowns."]),
    ("Origin Story", "The untold origin of {t}",
     ["The origin story of {t} begins somewhere nobody expects, and almost ended before it started.",
      "At first, {t} looked like a failure. Most people involved wanted to give up completely.",
      "Then one unexpected turn changed the future of {t} forever, almost overnight.",
      "From that moment, {t} grew into the thing the whole world knows today.",
      "Great things rarely start great. Follow for tomorrow's untold origin story."]),
    ("Why It Matters", "Why {t} matters to YOU",
     ["You might think {t} has nothing to do with your life. You would be wrong.",
      "Quietly, {t} is already shaping decisions you make every single day without realising it.",
      "Understanding {t} gives you an advantage most people around you simply do not have.",
      "Ignore {t}, and you miss the shift that is already happening right now.",
      "Save this video. Future you will be glad you understood {t} early."]),
    ("3 Mistakes", "3 mistakes everyone makes with {t}",
     ["Here are three mistakes almost everyone makes with {t}, and number three is the worst.",
      "Mistake one: rushing in without understanding the basics of {t} first.",
      "Mistake two: copying what everyone else does with {t}, instead of what actually works.",
      "Mistake three: giving up on {t} right before the results were about to show up.",
      "Avoid these three and {t} becomes ten times easier. Follow for more."]),
    ("By The Numbers", "{t} in numbers",
     ["Let us talk numbers, because the scale of {t} is honestly hard to believe.",
      "The numbers behind {t} are growing faster this year than almost anyone predicted.",
      "Compare where {t} started with where it is now, and the growth looks unreal.",
      "Experts believe the numbers for {t} will look even crazier in the next few years.",
      "Which number shocked you most? Tell me in the comments below."]),
    ("What If", "What if {t} disappeared tomorrow?",
     ["Imagine waking up tomorrow and {t} simply did not exist anymore. What breaks first?",
      "Within hours, the absence of {t} would hit things you never connected to it.",
      "Within days, people would scramble for replacements, and none would truly work.",
      "That is how deeply {t} is woven into normal life without us noticing.",
      "What would YOU miss most about {t}? Comment below."]),
    ("Future", "The future of {t} is wild",
     ["The future of {t} will look nothing like today, and the shift has already started.",
      "New ideas are pushing {t} in directions that sounded like science fiction recently.",
      "Early movers in {t} are positioning themselves while everyone else is still watching.",
      "In a few years, what seems advanced about {t} today will feel completely normal.",
      "Follow now, so you are early to where {t} is heading next."]),
    ("Quiz Hook", "Can you guess this about {t}?",
     ["Quick quiz. Pause and guess your answer about {t} before I reveal it.",
      "Most people guess the obvious answer, and most people are confidently wrong.",
      "Here is the real answer, and the reason behind it is the interesting part.",
      "That one detail explains so much about how {t} really behaves.",
      "Did you get it right? Be honest in the comments, and follow for daily quizzes."]),
    ("Beginner Guide", "{t} explained for total beginners",
     ["If {t} confuses you, watch this. I will explain it like you are five years old.",
      "Forget the jargon. At its heart, {t} is really about one simple idea.",
      "Think of {t} like something you already use daily, and suddenly it clicks.",
      "Once that picture is clear, every advanced part of {t} becomes easy to follow.",
      "Save this for the next time someone asks you about {t}."]),
    ("Hidden Secret", "The hidden secret of {t}",
     ["There is a hidden secret inside {t} that only insiders ever talk about.",
      "It is not hidden because it is complicated. It is hidden because nobody points at it.",
      "Once you see this part of {t}, so many confusing things suddenly make sense.",
      "And honestly, this is the part of {t} that makes the biggest difference.",
      "Now you know the secret too. Follow for one secret like this every day."]),
]


def offline_plan(topic, count=10):
    t = (topic or "this topic").strip().rstrip(".?")
    items = []
    for i in range(max(1, min(count, 20))):
        angle, title_t, texts = ANGLES[i % len(ANGLES)]
        scenes = [_make_scene(j, x.format(t=t)) for j, x in enumerate(texts)]
        items.append({
            "id": i + 1, "angle": angle, "title": title_t.format(t=t.title() if len(t) < 60 else t),
            "scenes": scenes, "include": True,
            "estimated_duration_sec": round(sum(s["duration"] for s in scenes), 1),
        })
    return {"topic": t, "items": items, "engine": "offline",
            "warnings": ["Offline angle-engine created hook-driven starter scripts. Edit any scene, or add a free Groq/Gemini key in AI Settings for fully topic-specific scripts."]}


SYSTEM = """You write viral vertical Shorts. Given ONE topic, return ONLY JSON:
{"items":[{"title":"punchy title","angle":"angle name","scenes":[{"title":"short","text":"12-18 words spoken in this scene","character":"Narrator","visual_prompt":"what to show","keywords":["a","b"],"animation":"word_highlight|typewriter|pop|fade_up|slide_left|zoom_focus|chart_bars","duration":7}]}]}
Make exactly N items, each a DIFFERENT angle/hook on the topic, each with 4-5 scenes, strong first-line hook, total under 55 seconds of speech each, end with a follow/save/share line."""


def _llm_plan(topic, count, provider, api_key, model):
    import requests
    sys = SYSTEM.replace("exactly N", f"exactly {count}")
    provider = (provider or "").lower()
    if provider in ("groq", "openrouter"):
        url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
        model = model or ("llama-3.3-70b-versatile" if provider == "groq" else "meta-llama/llama-3.3-70b-instruct:free")
        r = requests.post(url, timeout=120, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                          json={"model": model, "temperature": 0.8,
                                "messages": [{"role": "system", "content": sys}, {"role": "user", "content": f"Topic: {topic}"}]})
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
    elif provider == "gemini":
        model = model or "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        r = requests.post(url, timeout=120, json={"contents": [{"parts": [{"text": sys + f"\n\nTopic: {topic}"}]}]})
        r.raise_for_status()
        raw = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    else:
        raise ValueError(provider)
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    data = json.loads(raw)
    items = []
    for i, it in enumerate(data.get("items", [])):
        scenes = []
        for j, s in enumerate(it.get("scenes", [])):
            base = _make_scene(j, s.get("text", ""), s.get("character", "Narrator"), s.get("title"))
            base.update({k: s[k] for k in ("visual_prompt", "keywords", "animation", "duration") if s.get(k)})
            scenes.append(base)
        if scenes:
            items.append({"id": i + 1, "angle": it.get("angle", f"Angle {i+1}"), "title": it.get("title", f"Short {i+1}"),
                          "scenes": scenes, "include": True,
                          "estimated_duration_sec": round(sum(float(s['duration']) for s in scenes), 1)})
    if not items:
        raise ValueError("AI returned no shorts")
    return {"topic": topic, "items": items[:count], "engine": provider, "warnings": []}


def bulk_plan(topic, count=10, provider="offline", api_key="", model=""):
    if provider and provider != "offline" and api_key:
        try:
            return _llm_plan(topic, count, provider, api_key, model)
        except Exception as e:
            out = offline_plan(topic, count)
            out["warnings"] = [f"Free AI ({provider}) failed: {e}. Fell back to offline angle-engine."] + out["warnings"]
            return out
    return offline_plan(topic, count)
