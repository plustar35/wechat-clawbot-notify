#!/usr/bin/env python3
"""
WeChat ClawBot Message Sender via iLink API.

Usage:
    send_wechat.py send "消息内容"          # 发送文本消息
    send_wechat.py refresh                  # 刷新 context_token
    send_wechat.py status                   # 查看当前 token 状态

Configuration is read from WorkBuddy settings.json automatically.
context_token is cached to <SKILL_DIR>/.token_cache.json
"""

import json
import os
import sys
import time
import uuid
import base64
import urllib.request
import urllib.error

if sys.version_info < (3, 8):
    print("Error: Python 3.8 or newer is required.", file=sys.stderr)
    sys.exit(1)

# --- Paths ---
SKILL_DIR = os.environ.get("SKILL_DIR", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_FILE = os.path.join(SKILL_DIR, ".token_cache.json")
LOG_FILE = os.path.join(SKILL_DIR, "logs", "send_wechat.log")
CHANNEL_VERSION = "workbuddy-desktop-1.0.0"

def _workbuddy_settings_candidates():
    # WorkBuddy itself resolves its config dir as WORKBUDDY_CONFIG_DIR (or the older
    # CODEBUDDY_CONFIG_DIR), falling back to <home>/.workbuddy on every platform.
    # On Windows <home> is %USERPROFILE%, e.g. C:\Users\<name>\.workbuddy\settings.json.
    env_dir = (os.environ.get("WORKBUDDY_CONFIG_DIR") or os.environ.get("CODEBUDDY_CONFIG_DIR") or "").strip()
    env_candidates = [os.path.join(env_dir, "settings.json")] if env_dir else []
    return env_candidates + _workbuddy_default_settings_candidates()


def _workbuddy_default_settings_candidates():
    if sys.platform == "darwin":
        return [
            os.path.expanduser("~/.workbuddy/settings.json"),
            os.path.expanduser("~/Library/Application Support/WorkBuddy/User/settings.json"),
        ]
    if sys.platform == "win32":
        candidates = []
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            candidates.append(os.path.join(userprofile, ".workbuddy", "settings.json"))
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(os.path.join(appdata, "WorkBuddy", "User", "settings.json"))
        if candidates:
            return candidates
        return [os.path.expanduser("~/AppData/Roaming/WorkBuddy/User/settings.json")]
    return [
        os.path.expanduser("~/.workbuddy/settings.json"),
        os.path.expanduser("~/.config/WorkBuddy/User/settings.json"),
    ]


def _extract_weixin_clawbot_config(settings):
    """Locate the weixinClawBot channel config inside a WorkBuddy settings dict.

    WorkBuddy has shipped three layouts:
      1. settings["claw.channels"]["weixinClawBot"]                        (flat key, legacy app dir)
      2. settings["claw"]["channels"]["weixinClawBot"]                     (nested, ~/.workbuddy)
      3. settings["claw"]["users"][<uid>]["channels"]["weixinClawBot"]     (per-user, WorkBuddy >= 5.5)
    Layout 3 wins when present. ``claw.legacyOwnerUid`` picks the user; otherwise
    the first user with an enabled weixinClawBot channel is used.
    """
    claw = settings.get("claw")
    if isinstance(claw, dict):
        users = claw.get("users")
        if isinstance(users, dict) and users:
            owner = claw.get("legacyOwnerUid")
            ordered = ([owner] if owner in users else []) + [u for u in users if u != owner]
            for uid in ordered:
                user = users.get(uid)
                channels = user.get("channels") if isinstance(user, dict) else None
                cfg = channels.get("weixinClawBot") if isinstance(channels, dict) else None
                if isinstance(cfg, dict) and cfg.get("enabled"):
                    return cfg

    channels = settings.get("claw.channels")
    if not isinstance(channels, dict) and isinstance(claw, dict):
        channels = claw.get("channels", {})
    if not isinstance(channels, dict):
        return {}
    cfg = channels.get("weixinClawBot", {})
    return cfg if isinstance(cfg, dict) else {}


WORKBUDDY_SETTINGS = _workbuddy_settings_candidates()[0]


def log(message):
    """Append-only action log."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{ts}\t{message}\n")


def load_config():
    """Load ClawBot config from WorkBuddy settings."""
    errors = []
    bot_cfg = {}
    settings_path = None

    for candidate in _workbuddy_settings_candidates():
        try:
            with open(candidate, "r", encoding="utf-8-sig") as f:
                settings = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            errors.append(f"{candidate}: {e}")
            continue

        candidate_cfg = _extract_weixin_clawbot_config(settings)
        if candidate_cfg.get("enabled"):
            bot_cfg = candidate_cfg
            settings_path = candidate
            break

    if not settings_path:
        detail = "; ".join(errors) if errors else "weixinClawBot channel is not enabled"
        print(f"Error: Cannot read WorkBuddy settings: {detail}", file=sys.stderr)
        sys.exit(1)

    if not bot_cfg.get("enabled"):
        print("Error: weixinClawBot channel is not enabled in WorkBuddy settings.", file=sys.stderr)
        sys.exit(1)

    required = ["botToken", "baseUrl", "userId"]
    for key in required:
        if not bot_cfg.get(key):
            print(f"Error: Missing '{key}' in weixinClawBot config.", file=sys.stderr)
            sys.exit(1)

    bot_cfg["_settings_path"] = settings_path
    return bot_cfg


def generate_wechat_uin():
    """Generate X-WECHAT-UIN header: random uint32 -> decimal string -> base64."""
    rand_uint32 = int.from_bytes(os.urandom(4), "little")
    decimal_str = str(rand_uint32)
    return base64.b64encode(decimal_str.encode("ascii")).decode("ascii")


def make_headers(bot_token):
    """Build request headers for iLink API."""
    return {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Authorization": f"Bearer {bot_token}",
        "X-WECHAT-UIN": generate_wechat_uin(),
    }


def api_request(base_url, path, bot_token, payload, timeout=15):
    """Make a POST request to the iLink API."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = make_headers(bot_token)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        print(f"Error: HTTP {e.code} from {path}: {error_body}", file=sys.stderr)
        log(f"HTTP_ERROR\t{path}\t{e.code}\t{error_body[:200]}")
        return None
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", str(e))
        print(f"Error: Network error calling {path}: {reason}", file=sys.stderr)
        log(f"NETWORK_ERROR\t{path}\t{reason}")
        return None


def load_cached_token(config):
    """Load cached context_token from disk."""
    cache = load_cache()
    if not cache or not cache_matches_config(cache, config):
        return None
    return cache.get("context_token")


def cache_matches_config(cache, config):
    """Return whether a cache entry belongs to the active ClawBot account."""
    cached_account_id = cache.get("account_id")
    if not cached_account_id:
        return True
    return cached_account_id == config.get("accountId")


def load_cache():
    """Load the cache file, tolerating legacy or malformed cache state."""
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_cached_token(token):
    """Save context_token to disk (convenience wrapper)."""
    save_cache(context_token=token)


def load_getupdates_buf(config):
    """Load the getupdates cursor from cache."""
    cache = load_cache()
    if not cache:
        return ""

    # Legacy caches did not record account_id. Keep legacy context_token usable,
    # but ignore legacy cursors because they can belong to a different bot and
    # iLink may reject them with ret=-14 after WorkBuddy reconnects/migrates.
    if not cache.get("account_id"):
        return ""

    if not cache_matches_config(cache, config):
        return ""
    return cache.get("get_updates_buf", "")


def save_cache(context_token=None, get_updates_buf=None, config=None):
    """Save context_token and/or get_updates_buf to disk."""
    cache = load_cache()

    if context_token is not None:
        cache["context_token"] = context_token
    if get_updates_buf is not None:
        cache["get_updates_buf"] = get_updates_buf
    if config is not None:
        cache["account_id"] = config.get("accountId")
        cache["settings_path"] = config.get("_settings_path")
    cache["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def refresh_token(config, retry_without_cursor=True):
    """Fetch latest messages via getupdates to extract a fresh context_token.

    getupdates is a long-polling endpoint (holds up to 35s).
    Uses get_updates_buf as cursor for pagination.
    """
    buf = load_getupdates_buf(config)
    payload = {
        "get_updates_buf": buf,
        "base_info": {"channel_version": CHANNEL_VERSION}
    }

    # getupdates holds connection up to 35s waiting for new messages
    print("Polling for messages (may take up to 35 seconds)...", file=sys.stderr)
    result = api_request(
        config["baseUrl"], "/ilink/bot/getupdates", config["botToken"],
        payload, timeout=45
    )

    if result is None:
        return None

    ret = result.get("ret", None)
    if ret is not None and ret != 0:
        print(f"Warning: getupdates returned ret={ret}", file=sys.stderr)
        log(f"TOKEN_REFRESH_FAILED\tret={ret}")
        if retry_without_cursor and buf:
            print("Retrying refresh without cached get_updates_buf...", file=sys.stderr)
            save_cache(get_updates_buf="", config=config)
            return refresh_token(config, retry_without_cursor=False)
        return None

    # Save the new cursor for next call
    new_buf = result.get("get_updates_buf", "")
    if new_buf:
        save_cache(get_updates_buf=new_buf, config=config)

    # Extract context_token from messages
    messages = result.get("msgs", [])

    if messages:
        for msg in reversed(messages):  # Most recent last
            token = msg.get("context_token", "")
            if token:
                save_cache(context_token=token, config=config)
                log(f"TOKEN_REFRESHED\t{token[:32]}...")
                print(f"Found {len(messages)} message(s).", file=sys.stderr)
                return token

    print("Warning: No messages with context_token found.", file=sys.stderr)
    print("Please send a message to your ClawBot in WeChat first, then run 'refresh' again.", file=sys.stderr)
    log("TOKEN_REFRESH_FAILED\tno messages found")
    return None


def send_message(config, text, context_token):
    """Send a text message to the user via ClawBot.

    All fields are required per the iLink protocol spec.
    Missing any field causes silent failure (HTTP 200 but no delivery).
    """
    client_id = f"workbuddy-notify-{uuid.uuid4().hex[:16]}"

    payload = {
        "msg": {
            "from_user_id": "",
            "to_user_id": config["userId"],
            "client_id": client_id,
            "message_type": 2,
            "message_state": 2,
            "context_token": context_token,
            "item_list": [
                {
                    "type": 1,
                    "text_item": {
                        "text": text
                    }
                }
            ]
        },
        "base_info": {
            "channel_version": CHANNEL_VERSION
        }
    }

    result = api_request(config["baseUrl"], "/ilink/bot/sendmessage", config["botToken"], payload)

    if result is None:
        return False

    # Check for errors - API may use "ret" or "errcode", or return empty {} on success
    ret = result.get("ret", result.get("errcode", None))
    if ret is not None and ret != 0:
        errmsg = result.get("errmsg", result.get("err_msg", json.dumps(result)))
        print(f"Error: API returned ret={ret}: {errmsg}", file=sys.stderr)
        log(f"SEND_FAILED\tret={ret}\t{errmsg}")
        return False

    log(f"SEND_OK\t{text[:50]}")
    return True


def cmd_send(args):
    """Handle 'send' command."""
    if not args:
        print("Error: No message provided. Usage: send_wechat.py send \"消息内容\"", file=sys.stderr)
        sys.exit(1)

    text = " ".join(args)
    config = load_config()

    # Get context_token: try cache first, then refresh
    context_token = load_cached_token(config)
    if not context_token:
        print("No cached context_token. Attempting to refresh...", file=sys.stderr)
        context_token = refresh_token(config)
        if not context_token:
            print("Error: Cannot obtain context_token. Please send a message to your ClawBot in WeChat first.", file=sys.stderr)
            sys.exit(1)

    # Attempt to send
    success = send_message(config, text, context_token)

    if not success:
        # Try refreshing token and retry once
        print("Retrying with refreshed token...", file=sys.stderr)
        context_token = refresh_token(config)
        if context_token:
            success = send_message(config, text, context_token)

    if success:
        print(f"Message sent successfully: {text[:80]}")
    else:
        print("Error: Failed to send message after retry.", file=sys.stderr)
        sys.exit(1)


def cmd_refresh(_args):
    """Handle 'refresh' command."""
    config = load_config()
    token = refresh_token(config)
    if token:
        print(f"Token refreshed successfully: {token[:32]}...")
    else:
        print("Failed to refresh token. Send a message to ClawBot first.", file=sys.stderr)
        sys.exit(1)


def cmd_status(_args):
    """Handle 'status' command."""
    config = load_config()
    cache = load_cache() if os.path.exists(CACHE_FILE) else {}
    # load_cached_token() returns None when the cache belongs to a different bot,
    # so Ready reflects whether a *usable* token exists, not just any token.
    token = load_cached_token(config)
    stale_token = bool(cache.get("context_token")) and not token
    cache_account_id = cache.get("account_id", "legacy") if cache else "N/A"
    updated_at = cache.get("updated_at", "N/A") if cache else "N/A"

    print(f"Settings:  {config.get('_settings_path', WORKBUDDY_SETTINGS)}")
    print(f"Bot ID:    {config.get('accountId', 'N/A')}")
    print(f"User ID:   {config['userId']}")
    print(f"Base URL:  {config['baseUrl']}")
    print(f"Mode:      {config.get('connectionMode', 'N/A')}")
    print(f"Enabled:   {config.get('enabled', False)}")
    print(f"Ready:     {bool(token)}")

    if cache:
        print(f"Cache Bot: {cache_account_id}")
        if token:
            print(f"Token:     {token[:32]}...")
        elif stale_token:
            print(f"Token:     Cached for a different bot ({cache_account_id}); run 'refresh'")
        else:
            print("Token:     Not cached (run 'refresh' first)")
        print(f"Updated:   {updated_at}")
    else:
        print("Token:     Not cached (run 'refresh' first)")


COMMANDS = {
    "send": cmd_send,
    "refresh": cmd_refresh,
    "status": cmd_status,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__.strip())
        print("\nCommands:")
        print("  send <message>    Send a text message to WeChat ClawBot")
        print("  refresh           Refresh context_token from recent messages")
        print("  status            Show current configuration and token status")
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Error: Unknown command '{cmd}'. Use 'send', 'refresh', or 'status'.", file=sys.stderr)
        sys.exit(1)

    COMMANDS[cmd](sys.argv[2:])


if __name__ == "__main__":
    main()
