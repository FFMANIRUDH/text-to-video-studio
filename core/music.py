"""
Background music — 100% free & royalty-free because we SYNTHESIZE it ourselves.
5 built-in moods generated with numpy (pads + arpeggios), plus upload-your-own.
Auto-ducking: music automatically gets quieter while a character is speaking
and swells back up in the gaps (attack/release smoothed gain envelope).
"""
import wave
from pathlib import Path
import numpy as np

SR = 44100
ROOT = Path(__file__).resolve().parent.parent
MUSIC_DIR = ROOT / "outputs" / "music"

BUILTINS = [
    {"id": "cinematic", "label": "🎬 Cinematic Epic (built-in, free)"},
    {"id": "calm",      "label": "🌿 Calm Piano (built-in, free)"},
    {"id": "upbeat",    "label": "⚡ Upbeat Energy (built-in, free)"},
    {"id": "dark",      "label": "🌑 Dark Tension (built-in, free)"},
    {"id": "happy",     "label": "🎈 Happy / Kids (built-in, free)"},
]

# chord progressions as MIDI notes, per mood: (chords, tempo of arpeggio sec, brightness)
_MOODS = {
    "cinematic": ([[50, 53, 57], [46, 50, 53], [53, 57, 60], [48, 52, 55]], 0.55, 0.5),
    "calm":      ([[48, 52, 55, 59], [45, 48, 52, 55], [41, 45, 48, 52], [43, 47, 50, 55]], 0.8, 0.35),
    "upbeat":    ([[48, 52, 55], [43, 47, 50], [45, 48, 52], [41, 45, 48]], 0.3, 0.65),
    "dark":      ([[45, 48, 52], [44, 47, 51], [41, 45, 48], [43, 46, 50]], 0.9, 0.25),
    "happy":     ([[48, 52, 55], [41, 45, 48], [43, 47, 50], [48, 52, 55]], 0.4, 0.6),
}


def _midi(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def _add_note(buf, start, freq, dur, amp, bright=0.4):
    n = int(dur * SR)
    s = int(start * SR)
    if s >= len(buf):
        return
    n = min(n, len(buf) - s)
    t = np.arange(n) / SR
    env = np.minimum(1.0, t / 0.03) * np.exp(-t * 2.2)
    tone = np.sin(2 * np.pi * freq * t) + bright * np.sin(2 * np.pi * freq * 2 * t) + 0.12 * np.sin(2 * np.pi * freq * 3 * t)
    buf[s:s + n] += amp * env * tone


def generate_builtin(mood="cinematic", seconds=32):
    mood = mood if mood in _MOODS else "cinematic"
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    out = MUSIC_DIR / f"builtin-{mood}.wav"
    if out.exists() and out.stat().st_size > 100000:
        return out
    chords, arp_step, bright = _MOODS[mood]
    buf = np.zeros(int(seconds * SR), dtype=np.float64)
    seg = seconds / len(chords)
    rng = np.random.default_rng(abs(hash(mood)) % 9999)

    for ci, chord in enumerate(chords):
        start = ci * seg
        s0, s1 = int(start * SR), int((start + seg) * SR)
        t = np.arange(s1 - s0) / SR
        env = np.sin(np.pi * np.arange(s1 - s0) / max(1, (s1 - s0))) ** 1.5  # smooth pad swell
        pad = np.zeros(s1 - s0)
        for m in chord + [chord[0] - 12]:
            pad += np.sin(2 * np.pi * _midi(m) * t) * (0.16 if m == chord[0] - 12 else 0.10)
        buf[s0:s1] += pad * env
        # arpeggio / melody from chord tones an octave up
        steps = int(seg / arp_step)
        for k in range(steps):
            if mood in ("dark", "calm") and rng.random() < 0.35:
                continue
            note = chord[k % len(chord)] + 12 + (12 if (k % 7 == 6) else 0)
            _add_note(buf, start + k * arp_step, _midi(note), arp_step * 1.8, 0.16, bright)

    if mood == "upbeat":  # simple kick pulse
        for beat in np.arange(0, seconds, 0.6):
            _add_note(buf, float(beat), 65, 0.18, 0.35, 0.05)

    fade = int(1.2 * SR)
    buf[:fade] *= np.linspace(0, 1, fade)
    buf[-fade:] *= np.linspace(1, 0, fade)
    peak = np.max(np.abs(buf)) or 1
    buf = buf / peak * 0.72
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((buf * 32767).astype(np.int16).tobytes())
    return out


def list_uploads():
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(MUSIC_DIR.iterdir()):
        if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a") and not p.name.startswith("builtin-"):
            out.append({"name": p.name, "url": f"/outputs/music/{p.name}"})
    return out


def _read_wav(path):
    with wave.open(str(path)) as w:
        n, ch, sr, sw = w.getnframes(), w.getnchannels(), w.getframerate(), w.getsampwidth()
        raw = w.readframes(n)
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[sw]
    a = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if sw == 1:
        a = (a - 128) / 128
    else:
        a = a / (2 ** (8 * sw - 1))
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, sr


def mix_with_ducking(voice_wav, music_wav, out_wav, volume=0.35, duck=0.8):
    """Loop music under the voice; duck it down while speech is active."""
    voice, sr = _read_wav(voice_wav)
    music, msr = _read_wav(music_wav)
    if msr != sr:  # simple linear resample
        idx = np.linspace(0, len(music) - 1, int(len(music) * sr / msr))
        music = np.interp(idx, np.arange(len(music)), music)
    if len(music) == 0:
        return voice_wav
    reps = int(np.ceil(len(voice) / len(music))) + 1
    music = np.tile(music, reps)[:len(voice)]
    fade = min(int(1.0 * sr), len(music) // 4)
    if fade > 0:
        music[:fade] *= np.linspace(0, 1, fade)
        music[-fade:] *= np.linspace(1, 0, fade)

    # speech-activity envelope (50ms chunks) -> smoothed ducking gain
    chunk = max(1, int(0.05 * sr))
    nch = int(np.ceil(len(voice) / chunk))
    gains = np.ones(nch)
    cur = 1.0
    low = max(0.04, 1.0 - float(duck))
    for i in range(nch):
        seg = voice[i * chunk:(i + 1) * chunk]
        rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
        target = low if rms > 0.015 else 1.0
        cur += (target - cur) * (0.45 if target < cur else 0.07)  # fast attack, slow release
        gains[i] = cur
    gain = np.repeat(gains, chunk)[:len(voice)]

    mix = voice + music * float(volume) * gain
    peak = np.max(np.abs(mix)) or 1
    if peak > 0.95:
        mix = mix / peak * 0.95
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(mix, -1, 1) * 32767).astype(np.int16).tobytes())
    return out_wav
