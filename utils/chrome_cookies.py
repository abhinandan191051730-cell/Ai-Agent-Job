"""Extract Chrome cookies from a running Chrome profile (read-only, no lock needed)."""
import json
import os
import sqlite3
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from utils.logger import get_logger

LINKEDIN_PROFILE = "Profile 7"

def _get_chrome_user_data() -> Optional[str]:
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data")
    return base if os.path.isdir(base) else None

def _ensure_cookies_accessible() -> bool:
    """Close Chrome if the cookie DB is locked, so we can read it."""
    user_data = _get_chrome_user_data()
    if not user_data:
        return False
    db = os.path.join(user_data, LINKEDIN_PROFILE, "Network", "Cookies")
    if not os.path.isfile(db):
        db = os.path.join(user_data, LINKEDIN_PROFILE, "Cookies")
    if not os.path.isfile(db):
        return False

    try:
        conn = sqlite3.connect(db, timeout=1)
        conn.execute("SELECT 1 FROM cookies LIMIT 1")
        conn.close()
        return True
    except Exception:
        pass

    logger = get_logger("chrome_cookies")
    logger.warning("Chrome's cookie DB is locked (Chrome running). Closing Chrome...")
    if platform.system() == "Windows":
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
        import time
        time.sleep(2)

    try:
        conn = sqlite3.connect(db, timeout=3)
        conn.execute("SELECT 1 FROM cookies LIMIT 1")
        conn.close()
        return True
    except Exception:
        return False

def _decrypt_key(local_state_path: str) -> Optional[bytes]:
    try:
        import win32crypt
        with open(local_state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        enc_key = state.get("os_crypt", {}).get("encrypted_key")
        if not enc_key:
            return None
        encrypted_key = bytes(enc_key, "utf-8") if isinstance(enc_key, str) else enc_key
        encrypted_key = encrypted_key.encode("utf-8") if isinstance(encrypted_key, str) else encrypted_key
        import base64
        decoded = base64.b64decode(encrypted_key)
        # Remove 'DPAPI' prefix
        assert decoded[:5] == b"DPAPI"
        return win32crypt.CryptUnprotectData(decoded[5:], None, None, None, 0)[1]
    except Exception as e:
        print(f"Failed to decrypt key: {e}")
        return None

def _decrypt_cookie(encrypted_value: bytes, key: bytes) -> str:
    try:
        if not encrypted_value or encrypted_value == b"":
            return ""
        if len(encrypted_value) < 32 or not encrypted_value[0:1] == b"v":
            return encrypted_value.decode("utf-8", errors="replace")
        prefix_len = 3
        nonce = encrypted_value[prefix_len:prefix_len + 12]
        ciphertext = encrypted_value[prefix_len + 12:]
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode("utf-8")
    except Exception:
        return ""

def get_cookies_for_domain(domain_filter: str = "") -> list[dict]:
    """Extract decrypted cookies from Chrome's cookie DB.
    
    Returns list of cookie dicts compatible with Playwright's context.add_cookies().
    """
    user_data = _get_chrome_user_data()
    if not user_data:
        return []

    if not _ensure_cookies_accessible():
        logger = get_logger("chrome_cookies")
        logger.error("Cannot access Chrome cookie DB")
        return []

    local_state = os.path.join(user_data, "Local State")
    key = _decrypt_key(local_state)
    if not key:
        return []

    cookies_db = os.path.join(user_data, LINKEDIN_PROFILE, "Network", "Cookies")
    if not os.path.isfile(cookies_db):
        cookies_db = os.path.join(user_data, LINKEDIN_PROFILE, "Cookies")

    cookies = []
    try:
        conn = sqlite3.connect(cookies_db)
        conn.text_factory = bytes
        query = "SELECT host_key, name, value, path, expires_utc, is_secure, is_httponly, samesite, encrypted_value, has_expires FROM cookies"
        params = []
        if domain_filter:
            query += " WHERE host_key LIKE ?"
            params.append(f"%{domain_filter}%")
        for row in conn.execute(query, params):
            host_key = row[0].decode("utf-8") if isinstance(row[0], bytes) else row[0]
            name = row[1].decode("utf-8") if isinstance(row[1], bytes) else row[1]
            path = row[3].decode("utf-8") if isinstance(row[3], bytes) else row[3]
            encrypted_value = row[8]
            has_expires = row[9]

            decrypted = _decrypt_cookie(encrypted_value, key)
            if decrypted is None:
                continue

            if not decrypted:
                continue
            if not name or not host_key:
                continue

            domain = host_key
            if domain.startswith("."):
                domain = domain[1:]

            cookie = {
                "name": name,
                "value": decrypted,
                "domain": domain,
                "path": path or "/",
                "secure": bool(row[5]),
                "httpOnly": bool(row[6]),
            }

            same_site = row[7] if isinstance(row[7], int) else -1
            if same_site == 1:
                cookie["sameSite"] = "Lax"
            elif same_site == 2:
                cookie["sameSite"] = "Strict"
            else:
                cookie["sameSite"] = "None"

            if has_expires:
                expires = row[4]
                if isinstance(expires, (int, float)) and expires > 0:
                    expires_sec = expires / 1000000 - 11644473600
                    if expires_sec > 0:
                        cookie["expires"] = expires_sec

            cookies.append(cookie)
        conn.close()
    except Exception as e:
        print(f"Error reading cookies: {e}")
        return []

    return cookies


SESSION_COOKIES = {"li_at", "JSESSIONID", "li_a", "liap", "li_sugr", "lidc", "bcookie", "bscookie", "lang", "timezone", "UserMatchHistory", "lms_analytics", "AnalyticsSyncHistory"}

def _match_domain(cookie_domain: str, current_domain: str) -> bool:
    """Check if cookie domain matches or is a parent of the current domain."""
    if cookie_domain == current_domain:
        return True
    if cookie_domain.startswith("."):
        cookie_domain = cookie_domain[1:]
    if current_domain.endswith(f".{cookie_domain}"):
        return True
    if cookie_domain == current_domain:
        return True
    return False

async def inject_linkedin_cookies(page) -> bool:
    """Inject LinkedIn cookies from Chrome into a Playwright page."""
    cookies = get_cookies_for_domain("linkedin")
    li_cookies = [c for c in cookies if c["name"] in SESSION_COOKIES and "linkedin.com" in c["domain"]]
    if li_cookies:
        has_li_at = any(c["name"] == "li_at" for c in li_cookies)
        # Inject in batches of 10 to avoid request size limits
        for i in range(0, len(li_cookies), 10):
            batch = li_cookies[i:i+10]
            try:
                await page.context.add_cookies(batch)
            except Exception as e:
                logger = get_logger("chrome_cookies")
                logger.warning("Failed to inject batch %d: %s", i // 10, e)
        return has_li_at
    return False
