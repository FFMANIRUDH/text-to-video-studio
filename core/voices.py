"""Free voices via Microsoft Edge TTS (no API key) + description -> voice matching."""
import asyncio, re
from pathlib import Path

VOICES = [
    {"id": "en-IN-NeerjaNeural",      "label": "Neerja — English (India, F)",   "lang": "en-IN", "gender": "feminine",  "traits": "clear warm Indian young narrator"},
    {"id": "en-IN-PrabhatNeural",     "label": "Prabhat — English (India, M)",  "lang": "en-IN", "gender": "masculine", "traits": "clear calm Indian narrator documentary"},
    {"id": "en-US-JennyNeural",       "label": "Jenny — English (US, F)",       "lang": "en-US", "gender": "feminine",  "traits": "friendly energetic young American"},
    {"id": "en-US-AriaNeural",        "label": "Aria — English (US, F)",        "lang": "en-US", "gender": "feminine",  "traits": "confident bright expressive American"},
    {"id": "en-US-GuyNeural",         "label": "Guy — English (US, M)",         "lang": "en-US", "gender": "masculine", "traits": "energetic friendly young American"},
    {"id": "en-US-ChristopherNeural", "label": "Christopher — English (US, M)", "lang": "en-US", "gender": "masculine", "traits": "deep serious calm authoritative old narrator"},
    {"id": "en-US-EricNeural",        "label": "Eric — English (US, M)",        "lang": "en-US", "gender": "masculine", "traits": "raspy mature storyteller"},
    {"id": "en-GB-SoniaNeural",       "label": "Sonia — English (UK, F)",       "lang": "en-GB", "gender": "feminine",  "traits": "British elegant calm teacher"},
    {"id": "en-GB-RyanNeural",        "label": "Ryan — English (UK, M)",        "lang": "en-GB", "gender": "masculine", "traits": "British deep documentary narrator"},
    {"id": "te-IN-ShrutiNeural",      "label": "Shruti — Telugu (F)",           "lang": "te-IN", "gender": "feminine",  "traits": "Telugu warm clear narrator"},
    {"id": "te-IN-MohanNeural",       "label": "Mohan — Telugu (M)",            "lang": "te-IN", "gender": "masculine", "traits": "Telugu calm clear narrator"},
    {"id": "hi-IN-SwaraNeural",       "label": "Swara — Hindi (F)",             "lang": "hi-IN", "gender": "feminine",  "traits": "Hindi warm expressive narrator"},
    {"id": "hi-IN-MadhurNeural",      "label": "Madhur — Hindi (M)",            "lang": "hi-IN", "gender": "masculine", "traits": "Hindi deep calm narrator"},
    {"id": "ta-IN-PallaviNeural",     "label": "Pallavi — Tamil (F)",           "lang": "ta-IN", "gender": "feminine",  "traits": "Tamil clear narrator"},
    {"id": "ta-IN-ValluvarNeural",    "label": "Valluvar — Tamil (M)",          "lang": "ta-IN", "gender": "masculine", "traits": "Tamil deep narrator"},
]

FEMALE_WORDS = {"female", "woman", "girl", "she", "her", "mother", "grandmother", "queen", "princess", "actress", "lady"}
MALE_WORDS = {"male", "man", "boy", "he", "his", "father", "grandfather", "king", "prince", "actor", "old man"}


def derive_prosody(description: str):
    """Turn words like 'energetic young' / 'slow old deep' into rate & pitch."""
    d = (description or "").lower()
    rate, pitch = 0, 0
    if any(w in d for w in ["energetic", "excited", "fast", "hyper", "cheerful"]): rate += 12
    if any(w in d for w in ["calm", "slow", "soft", "gentle", "relaxed"]): rate -= 10
    if any(w in d for w in ["old", "elderly", "grandfather", "grandmother"]): rate -= 12; pitch -= 15
    if any(w in d for w in ["young", "child", "kid", "teen"]): rate += 6; pitch += 25
    if any(w in d for w in ["deep", "heavy", "villain", "serious", "authoritative"]): pitch -= 25
    if any(w in d for w in ["high pitch", "cute", "sweet"]): pitch += 20
    rate = max(-50, min(50, rate)); pitch = max(-50, min(50, pitch))
    return f"{rate:+d}%", f"{pitch:+d}Hz"


def suggest_voice(description: str = "", gender: str = "", language: str = "en-IN"):
    d = (description or "").lower()
    if not gender:
        if any(w in d for w in FEMALE_WORDS): gender = "feminine"
        elif any(w in d for w in MALE_WORDS): gender = "masculine"
    lang_pref = language or "en-IN"
    if "Telugu" in d: lang_pref = "te-IN"
    elif "Hindi" in d: lang_pref = "hi-IN"
    elif "Tamil" in d: lang_pref = "ta-IN"
    elif "british" in d or "uk " in d: lang_pref = "en-GB"
    elif "american" in d: lang_pref = "en-US"

    words = set(re.findall(r"[a-z]+", d))
    best, best_score = VOICES[0], -1
    for v in VOICES:
        s = 0
        if v["lang"] == lang_pref: s += 5
        if gender and v["gender"] == gender: s += 5
        s += len(words & set(v["traits"].lower().split())) * 2
        if s > best_score: best, best_score = v, s
    rate, pitch = derive_prosody(description)
    return {"voice": best["id"], "voice_label": best["label"], "rate": rate, "pitch": pitch, "gender": best["gender"], "language": best["lang"]}


async def _edge_save(text, voice, rate, pitch, out_path):
    import edge_tts
    try:
        comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    except TypeError:
        comm = edge_tts.Communicate(text, voice)
    await comm.save(str(out_path))


def synthesize(text: str, voice: str, rate: str, pitch: str, out_path: Path) -> bool:
    """Generate speech mp3 with free Edge-TTS. Returns False if it fails (offline etc)."""
    text = (text or "").strip()
    if not text:
        return False
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(_edge_save(text[:1200], voice or "en-IN-PrabhatNeural", rate or "+0%", pitch or "+0Hz", out_path))
        return out_path.exists() and out_path.stat().st_size > 500
    except Exception:
        return False
