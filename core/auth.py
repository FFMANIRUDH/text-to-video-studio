"""
Google Sign-In verification + lightweight signed sessions.

Flow (Google Identity Services, no client-secret needed):
  Browser gets a Google ID token -> POST /api/auth/google
  -> we verify it with Google's tokeninfo endpoint (audience/issuer/expiry)
  -> we issue our own HMAC-signed session token (30 days).

Set GOOGLE_CLIENT_ID in the environment to lock the app to your own
OAuth client. If unset, the client id sent by the browser is used as the
expected audience (handy for personal/local use).
"""
import base64, hashlib, hmac, json, os, secrets, time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SECRET_FILE = BASE / "data" / ".app_secret"
GUEST = {"id": "guest", "name": "Guest", "email": "", "picture": "", "guest": True}


def _secret() -> bytes:
    env = os.environ.get("APP_SECRET")
    if env:
        return env.encode()
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not SECRET_FILE.exists():
        SECRET_FILE.write_text(secrets.token_urlsafe(48))
    return SECRET_FILE.read_text().strip().encode()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s.encode())


def make_session(user: dict, days: int = 30) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user["id"], "email": user.get("email", ""), "name": user.get("name", ""),
        "picture": user.get("picture", ""), "iat": int(time.time()),
        "exp": int(time.time()) + days * 86400,
    }
    signing = f"{_b64e(json.dumps(header).encode())}.{_b64e(json.dumps(payload).encode())}"
    sig = hmac.new(_secret(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64e(sig)}"


def parse_session(token: str):
    try:
        head, body, sig = str(token).split(".")
        expected = hmac.new(_secret(), f"{head}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(sig)):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("exp", 0)) < time.time():
            return None
        return {"id": payload["sub"], "email": payload.get("email", ""),
                "name": payload.get("name", ""), "picture": payload.get("picture", ""), "guest": False}
    except Exception:
        return None


def extract_token(headers, cookies) -> str:
    authz = headers.get("authorization") or headers.get("Authorization") or ""
    if authz.lower().startswith("bearer "):
        return authz[7:].strip()
    return cookies.get("ttv_session", "") if cookies else ""


def verify_google_id_token(id_token: str, client_id_from_browser: str = "") -> dict:
    import requests
    if not id_token:
        raise ValueError("Missing Google ID token")
    r = requests.get("https://oauth2.googleapis.com/tokeninfo",
                     params={"id_token": id_token}, timeout=20)
    if r.status_code != 200:
        raise ValueError("Google could not verify this sign-in. Please try again.")
    info = r.json()
    expected_aud = os.environ.get("GOOGLE_CLIENT_ID") or client_id_from_browser
    if expected_aud and info.get("aud") != expected_aud:
        raise ValueError("Google Client ID mismatch — the token was not issued for this app.")
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Invalid token issuer")
    if int(info.get("exp", 0)) < time.time():
        raise ValueError("Google sign-in expired — please sign in again.")
    sub = info.get("sub")
    if not sub:
        raise ValueError("Google did not return a user id")
    return {
        "id": f"google_{sub}",
        "provider": "google",
        "sub": sub,
        "email": info.get("email", ""),
        "email_verified": str(info.get("email_verified", "false")).lower() == "true",
        "name": info.get("name") or info.get("email", "Google User"),
        "picture": info.get("picture", ""),
        "guest": False,
    }
