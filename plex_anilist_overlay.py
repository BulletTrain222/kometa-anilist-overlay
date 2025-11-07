import requests
import yaml
import time
import json
import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from plexapi.server import PlexServer
import pytz
from difflib import SequenceMatcher
import hashlib
from collections import deque
from time import monotonic, sleep


# ===== CONFIG =====
ANILIST_TOKEN = os.getenv("ANILIST_TOKEN")
PLEX_URL = os.getenv("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
LIBRARY_NAME = os.getenv("LIBRARY_NAME", "Anime")
# File output locations
OVERLAY_WEEKDAY_FILE = os.getenv("OVERLAY_WEEKDAY_FILE", "/config/overlays/weekday_overlays.yml")
OVERLAY_COUNTDOWN_FILE = os.getenv("OVERLAY_COUNTDOWN_FILE", "/config/overlays/countdown_overlays.yml")
OVERLAY_AUDIO_FILE = os.getenv("OVERLAY_AUDIO_FILE", "/config/overlays/audio_overlays.yml")
CACHE_FILE = os.getenv("CACHE_FILE", "/config/anilist_cache.json")
MANUAL_EXCEPTIONS_FILE = os.getenv("MANUAL_EXCEPTIONS_FILE", "/config/manual_exceptions.json")
# Overlay feature toggles - control which overlays are generated
ENABLE_WEEKDAY_OVERLAY = os.getenv("ENABLE_WEEKDAY_OVERLAY", "true").lower() == "true"
ENABLE_COUNTDOWN_OVERLAY = os.getenv("ENABLE_COUNTDOWN_OVERLAY", "true").lower() == "true"
ENABLE_AUDIO_OVERLAY = os.getenv("ENABLE_AUDIO_OVERLAY", "true").lower() == "true"
# Behavioral and timing settings
RATE_LIMIT_DELAY = int(os.getenv("RATE_LIMIT_DELAY", 5))
ANILIST_RPM = int(os.getenv("ANILIST_RPM", 30))
ANILIST_TIMEOUT = int(os.getenv("ANILIST_TIMEOUT", 20))
CACHE_EXPIRY_HOURS = int(os.getenv("CACHE_EXPIRY_HOURS", 120))
CACHE_EXPIRY_HOURS_ANILIST = int(os.getenv("CACHE_EXPIRY_HOURS_ANILIST", 72))
CACHE_EXPIRY_HOURS_AUDIO = int(os.getenv("CACHE_EXPIRY_HOURS_AUDIO", 12))
LOCAL_TZ = pytz.timezone(os.getenv("TZ", "UTC"))
ANILIST_DEBUG = os.getenv("ANILIST_DEBUG", "false").lower() == "true"
MAX_AIR_DAYS = int(os.getenv("MAX_AIR_DAYS", 14))
FORCE_REFRESH = os.getenv("FORCE_REFRESH", "false").lower() == "true"
CLEAN_MISSING_FROM_PLEX = os.getenv("CLEAN_MISSING_FROM_PLEX", "false").lower() == "true"

# ===== LOGGING =====
LOG_FILE = os.getenv("LOG_FILE", "/config/logs/anilist_overlay.log")
MAX_LOG_SIZE = int(os.getenv("MAX_LOG_SIZE", 5 * 1024 * 1024))
BACKUP_COUNT = int(os.getenv("BACKUP_COUNT", 7))

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logger = logging.getLogger("anilist_overlay")
logger.setLevel(logging.DEBUG if ANILIST_DEBUG else logging.INFO)
file_handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_LOG_SIZE, backupCount=BACKUP_COUNT, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# ===== FILE HASH =====
def hash_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except:
        return "?"

# ===== CACHE HANDLERS =====
def load_cache():
    if os.path.exists(CACHE_FILE): # Check if cache file exists
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f: # Open cache file in read mode
                data = json.load(f)
                logger.info(f"🗂️  Loaded cache with {len(data)} entries.") # Log number of cached entries
                return data
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
    return {}

def save_cache(cache):
    try:
        tmp_file = CACHE_FILE + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, CACHE_FILE)
        logger.info(f"💾 Cache saved successfully ({len(cache)} entries).")
        logger.info(f"🧾 {CACHE_FILE} MD5: {hash_file(CACHE_FILE)}")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def is_cache_valid(entry, expiry_hours=None):
    """Validate cache entry using either global or override expiry (in hours)."""
    try:
        ts_str = entry.get("timestamp")
        if not ts_str:
            return False

        ts = datetime.fromisoformat(ts_str)
        now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()
        hours = expiry_hours if expiry_hours is not None else CACHE_EXPIRY_HOURS

        # Time-based expiry
        if (now - ts) >= timedelta(hours=hours):
            return False

        # Special rule: invalidate AniList results after air date passes
        result = entry.get("result", {})
        air_local_str = result.get("air_datetime_local")
        if air_local_str:
            try:
                air_local = datetime.strptime(air_local_str, "%Y-%m-%d %H:%M:%S")
                if now.date() > air_local.date():
                    return False
            except Exception:
                pass

        return True
    except Exception:
        return False



# ===== MANUAL EXCEPTIONS =====
def load_manual_exceptions():
    """Load manual title overrides or skip rules."""
    if not os.path.exists(MANUAL_EXCEPTIONS_FILE):
        logger.info(f"⚙️ No manual exceptions file found at {MANUAL_EXCEPTIONS_FILE}")
        return {}

    try:
        with open(MANUAL_EXCEPTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"🧩 Loaded manual exceptions ({len(data)} entries).")
            return data
    except Exception as e:
        logger.error(f"Failed to load manual exceptions: {e}")
        return {}

# ===== PLEX CONNECTION =====
def connect_plex(retries=5, delay=20):
    for attempt in range(1, retries + 1):
        try:
            plex = PlexServer(PLEX_URL, PLEX_TOKEN)
            logger.info(f"✅ Connected to Plex successfully on attempt {attempt}.")
            return plex
        except Exception as e:
            if attempt < retries:
                logger.warning(f"⚠️  Plex connection failed ({e}) — retrying in {delay}s (attempt {attempt}/{retries})...")
                time.sleep(delay)
            else:
                logger.error("❌ Could not connect to Plex after multiple attempts.")
                raise


# ===== AUDIO COUNT =====
def get_audio_counts(show):
    eng_count = 0
    jpn_count = 0

    for ep in show.episodes():
        try:
            # reload the full episode metadata (includes Media & Streams)
            ep.reload(includeAll=True)
            for media in ep.media:
                for part in media.parts:
                    for s in part.streams:
                        if getattr(s, "streamType", None) == 2:  # audio only
                            lang = (s.languageCode or s.languageTag or "").lower()
                            if lang in ["en", "eng"]:
                                eng_count += 1
                            elif lang in ["ja", "jpn"]:
                                jpn_count += 1
        except Exception as e:
            logger.debug(f"⚠️ Audio scan error for {show.title}: {e}")
            continue

    return eng_count, jpn_count


# ===== ANILIST RATE LIMITER + REQUEST WRAPPER =====
_RATE_WINDOW = 60.0
_request_times = deque()

def _ratelimit_gate(limit_per_min: int):
    """Block until we're allowed to make a request (sliding window + min spacing)."""
    now = monotonic()

    # Drop old timestamps outside the 60s window
    while _request_times and (now - _request_times[0]) > _RATE_WINDOW:
        _request_times.popleft()

    # If we already hit limit inside window, wait until the oldest expires
    if len(_request_times) >= limit_per_min:
        sleep_for = _RATE_WINDOW - (now - _request_times[0]) + 0.05
        logger.debug(f"⏳ Waiting {sleep_for:.2f}s to respect {limit_per_min}/min window")
        sleep(max(0.0, sleep_for))

    # Burst spacing: keep at least 60/limit seconds between calls
    min_spacing = _RATE_WINDOW / max(1, limit_per_min)
    if _request_times:
        elapsed = monotonic() - _request_times[-1]
        if elapsed < min_spacing:
            to_sleep = min_spacing - elapsed
            logger.debug(f"⏱️ Spacing sleep {to_sleep:.2f}s (burst limiter)")
            sleep(to_sleep)

def _record_request():
    _request_times.append(monotonic())

def anilist_request(query: str, variables: dict, headers: dict):
    """Call AniList with rate limiting and 429 handling."""
    while True:
        # Gate by our own limiter first
        _ratelimit_gate(ANILIST_RPM)

        try:
            resp = requests.post(
                "https://graphql.anilist.co",
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=ANILIST_TIMEOUT,
            )
        except Exception as e:
            # brief jittered retry on transport errors
            logger.warning(f"🌐 AniList transport error: {e}; retrying in 2s")
            sleep(2.0)
            continue

        # 429 hard limit — honor Retry-After / Reset
        if resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            reset = resp.headers.get("X-RateLimit-Reset")
            if ra and ra.isdigit():
                wait_s = int(ra)
                logger.warning(f"🚦 429 Too Many Requests — sleeping {wait_s}s per Retry-After")
                sleep(wait_s)
            elif reset and reset.isdigit():
                reset_ts = int(reset)
                wait_s = max(0, reset_ts - int(time.time())) + 1
                logger.warning(f"🚦 429 Too Many Requests — sleeping until reset ({wait_s}s)")
                sleep(wait_s)
            else:
                logger.warning("🚦 429 Too Many Requests — sleeping 60s (no headers)")
                sleep(60)
            # loop and try again
            continue

        # Successful response (or other non-429)
        try:
            lim = int(resp.headers.get("X-RateLimit-Limit", ANILIST_RPM))
            rem = int(resp.headers.get("X-RateLimit-Remaining", ANILIST_RPM))
            logger.info(f"🌐 AniList rate status: {rem}/{lim} requests remaining this minute")
            
            # Optional: if near limit, apply a soft cooldown
            if rem <= max(1, lim // 10):
                slot = _RATE_WINDOW / max(1, lim)
                logger.warning(f"🪫 Near limit ({rem}/{lim}) — soft-sleep {slot:.2f}s to avoid 429")
                sleep(slot)
        except Exception as e:
            logger.debug(f"⚠️ Could not read AniList rate headers: {e}")


        _record_request()
        return resp



# ===== CORE FUNCTION =====
def get_next_air_datetime(title, cache, counters, MANUAL_EXCEPTIONS):
    url = "https://graphql.anilist.co"
    query = '''
    query ($search: String) {
      Page(perPage: 10) {
        media(
          search: $search,
          type: ANIME,
          sort: POPULARITY_DESC,
          format_in: [TV, TV_SHORT, ONA, OVA]
        ) {
          id
          title { romaji english native }
          synonyms
          format
          status
          averageScore
          nextAiringEpisode { airingAt episode }
        }
      }
    }
    '''
    variables = {"search": title}
    headers = {"Authorization": f"Bearer {ANILIST_TOKEN}"}

 # ===== MANUAL EXCEPTIONS CHECK (always override cache) =====
    if title in MANUAL_EXCEPTIONS:  # ← indented inside function now
        rule = MANUAL_EXCEPTIONS[title]
        logger.info(f"⚙️ Manual exception found for '{title}' — overriding cache")

        # Skip titles explicitly marked to ignore
        if rule is None or (isinstance(rule, str) and rule.lower() == "ignore"):
            logger.info(f"🚫 Skipping '{title}' (manual exception: ignore).")
            counters["no_airing"] += 1
            return {"weekday": "none"}, cache

        # Manual AniList ID override
        elif isinstance(rule, int):
            logger.info(f"🎯 Manual AniList override for '{title}' → ID {rule}")
            query = '''
            query ($id: Int) {
              Media(id: $id, type: ANIME) {
                id
                title { romaji english native }
                format
                status
                averageScore
                nextAiringEpisode { airingAt episode }
              }
            }
            '''
            variables = {"id": rule}

    else:  # ← also indented inside function
        # ===== CACHE CHECK =====
        if not FORCE_REFRESH and title in cache and is_cache_valid(cache[title]):
            counters["cache_used"] += 1
            logger.info(f"📦 Using CACHE for '{title}'")
            return cache[title]["result"], cache
        elif FORCE_REFRESH:
            logger.info(f"🔁 Force refresh enabled — ignoring cache for '{title}'")
        else:
            logger.info(f"🌐 Fetching from AniList API for '{title}'")


    result = {
        "weekday": "none",
        "air_datetime_utc": None,
        "air_datetime_local": None,
        "episode_number": None,
        "time_until_hours": None,
        "anilist_id": None,
        "e": None,
        "match_score": None,
        "averageScore": None,
        "matched_synonym": None
    }

    try:
        response = anilist_request(query, variables, headers)
        data = response.json()


        if "errors" in data:
            logger.warning(f"AniList error for '{title}': {data['errors'][0]['message']}")
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        # handle direct Media(id: X)
        if "data" in data and "Media" in data["data"]:
            media_list = [data["data"]["Media"]]
        else:
            media_list = data.get("data", {}).get("Page", {}).get("media", [])

        if not media_list:
            logger.warning(f"⚠️ No AniList matches found for '{title}'")
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        # ===== DETAILED DEBUG OUTPUT =====
        if ANILIST_DEBUG:
            logger.info(f"🔎 AniList results for '{title}':")
            for m in media_list:
                mid = m["id"]
                fmt = m.get("format", "UNKNOWN")
                mtitle = m["title"].get("romaji") or m["title"].get("english") or m["title"].get("native")
                status = m.get("status", "UNKNOWN")
                score = m.get("averageScore")
                airing = m.get("nextAiringEpisode")
                if airing:
                    air_time = datetime.fromtimestamp(airing["airingAt"], tz=pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                    logger.info(f"   🟢 ID {mid} | {mtitle} | {fmt} | {status} | Score: {score} | Ep {airing['episode']} @ {air_time}")
                else:
                    logger.info(f"   ⚪ ID {mid} | {mtitle} | {fmt} | {status} | Score: {score} | No upcoming episode")

        # ===== MATCHING LOGIC =====
        def similarity(a, b): return SequenceMatcher(None, a.lower(), b.lower()).ratio()
        best_match, best_score, matched_synonym = None, 0, None

        for media in media_list:
            candidates = []
            titles = media.get("title", {})
            for key in ["romaji", "english", "native"]:
                if titles.get(key):
                    candidates.append((titles[key], "title"))
            for s in (media.get("synonyms", []) or []):
                candidates.append((s, "synonym"))

            for candidate, ctype in candidates:
                score = 1.0 if candidate.strip().lower() == title.strip().lower() else similarity(title, candidate)
                if media.get("status") == "RELEASING":
                    score += 0.5
                if media.get("nextAiringEpisode"):
                    score += 0.4
                if not best_match or score > best_score:
                    best_match, best_score, matched_synonym = media, score, (candidate if ctype == "synonym" else None)

        if not best_match or best_score < 0.6:
            logger.warning(f"⚠️ No reliable AniList match for '{title}' (best={best_score:.2f})")
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        m = best_match
        logger.info(f"🎯 Selected {m['title'].get('romaji') or m['title'].get('english')} (status={m.get('status')}, score={best_score:.2f})")
        airing = m.get("nextAiringEpisode")

        if not airing:
            result.update({
                "anilist_id": m["id"],
                "e": m["title"].get("romaji") or m["title"].get("english") or m["title"].get("native"),
                "match_score": round(best_score, 3),
                "averageScore": m.get("averageScore"),
                "matched_synonym": matched_synonym
            })
            logger.info(f"🕒 '{title}' found on AniList (no upcoming episode listed)")
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        air_dt_utc = datetime.fromtimestamp(airing["airingAt"], tz=pytz.utc)
        air_dt_local = air_dt_utc.astimezone(LOCAL_TZ)
        hours_until = (air_dt_local - datetime.now(LOCAL_TZ)).total_seconds() / 3600

        result.update({
            "weekday": air_dt_local.strftime("%A").lower(),
            "air_datetime_utc": air_dt_utc.strftime("%Y-%m-%d %H:%M:%S"),
            "air_datetime_local": air_dt_local.strftime("%Y-%m-%d %H:%M:%S"),
            "episode_number": airing["episode"],
            "time_until_hours": round(hours_until, 1),
            "anilist_id": m["id"],
            "e": m["title"].get("romaji") or m["title"].get("english") or m["title"].get("native"),
            "match_score": round(best_score, 3),
            "averageScore": m.get("averageScore"),
            "matched_synonym": matched_synonym
        })

        counters["airing_found"] += 1
        logger.info(f"✅ AniList data fetched for '{title}' | Next Ep: {result['episode_number']} on {result['weekday'].capitalize()}")

    except Exception as e:
        logger.error(f"Error fetching '{title}': {e}")

    cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
    return result, cache

# ===== DAY LABEL =====
def get_day_label(days_until):
    if days_until <= 0: return "today"
    elif days_until == 1: return "tomorrow"
    elif days_until == 2: return "in_2_days"
    elif days_until == 3: return "in_3_days"
    elif days_until == 4: return "in_4_days"
    elif days_until == 5: return "in_5_days"
    elif days_until == 6: return "in_6_days"
    else: return "next_week"

# ===== TOKEN VALIDATION =====
def validate_anilist_token(token):
    try:
        r = requests.post(
            "https://graphql.anilist.co",
            json={"query": "{ Viewer { id name } }"},
            headers={"Authorization": f"Bearer {token}"}
        )
        if r.status_code == 200 and "data" in r.json():
            viewer = r.json()["data"].get("Viewer", {})
            return True, viewer.get("name", "Unknown User")
    except Exception as e:
        logger.debug(f"AniList token validation exception: {e}")
    return False, None

# ===== SYSTEM SUMMARY =====
def print_system_summary():
    logger.info("=== 🧠 AniList Overlay System Boot Summary ===")

    valid_token = False
    viewer_name = None
    if ANILIST_TOKEN:
        valid_token, viewer_name = validate_anilist_token(ANILIST_TOKEN)

    config_summary = {
        "Library": LIBRARY_NAME,
        "Timezone": LOCAL_TZ.zone,
        "AniList Token": (
            f"✅ Valid ({viewer_name})" if valid_token
            else ("⚠️ Could not validate" if ANILIST_TOKEN else "❌ Missing")
        ),
        "Plex URL": PLEX_URL,
        "Plex Token": "✅ Set" if PLEX_TOKEN else "❌ Missing",
        "Overlay (Weekday)": OVERLAY_WEEKDAY_FILE,
        "Overlay (Countdown)": OVERLAY_COUNTDOWN_FILE,
        "Manual Exceptions": MANUAL_EXCEPTIONS_FILE,
        "Cache File": CACHE_FILE,
        "Rate Limit Delay": f"{RATE_LIMIT_DELAY}s",
        "Cache Expiry": f"{CACHE_EXPIRY_HOURS}h",
        "Cache Expiry (AniList)": f"{CACHE_EXPIRY_HOURS_ANILIST}h",
        "Cache Expiry (Audio)": f"{CACHE_EXPIRY_HOURS_AUDIO}h",
        "Force Refresh": FORCE_REFRESH,
        "Max Air Days": MAX_AIR_DAYS,
        "Clean Missing from Plex": CLEAN_MISSING_FROM_PLEX,
        "Debug Mode": ANILIST_DEBUG,
        "Log File": LOG_FILE,
        "Log Max Size": f"{MAX_LOG_SIZE / 1024 / 1024:.1f} MB",
        "Log Backups": BACKUP_COUNT
    }

    max_key_len = max(len(k) for k in config_summary.keys())
    for key, val in config_summary.items():
        logger.info(f"  {key:<{max_key_len}} : {val}")

    logger.info("\n✅ Configuration Initialized Successfully — beginning AniList overlay sync...\n")

    if not ANILIST_TOKEN:
        logger.error("❌ Missing AniList token. Please set ANILIST_TOKEN.")
        raise SystemExit(1)
    if not valid_token:
        logger.warning("⚠️ AniList token validation failed — continuing anyway (API may reject requests).")
    if not PLEX_TOKEN:
        logger.error("❌ Missing Plex token. Please set PLEX_TOKEN.")
        raise SystemExit(1)

# ===== MAIN OVERLAY BUILDER =====
def build_overlay():
    start_time = time.time()
    logger.info("=== 🚀 Starting AniList → Kometa Overlay Update ===")
    logger.info(f"📦 Library: {LIBRARY_NAME}")
    logger.info(f"🕐 Cache Expiry: {CACHE_EXPIRY_HOURS}h | Rate Limit: {RATE_LIMIT_DELAY}s")

    plex = connect_plex()
    library = plex.library.section(LIBRARY_NAME)
    cache = load_cache()
    MANUAL_EXCEPTIONS = load_manual_exceptions()
    weekday_overlays, countdown_overlays = {}, {}
    now_local = datetime.now(LOCAL_TZ)
    counters = {"total": 0, "cache_used": 0, "api_calls": 0, "airing_found": 0, "no_airing": 0}

    # ===== PASS 1: BUILD AUDIO CACHE SEPARATELY =====
    logger.info("=== 🎧 Scanning Plex shows for audio track counts... ===")
    audio_cache = cache.get("_audio", {})

    for show in library.search(libtype="show"):
        title = show.title
        show_eps = len(show.episodes())

        audio_entry = audio_cache.get(title, {})
        cached_eng = audio_entry.get("english_audio_count", -1)
        cached_jpn = audio_entry.get("japanese_audio_count", -1)
        cached_eps = audio_entry.get("episode_count", -1)

        expired = not is_cache_valid(audio_entry, CACHE_EXPIRY_HOURS_AUDIO)
        needs_update = bool(
            expired
            or cached_eng == -1
            or cached_jpn == -1
            or cached_eps != show_eps
        )

        if needs_update:
            try:
                eng_count, jpn_count = get_audio_counts(show)
                audio_cache[title] = {
                    "english_audio_count": eng_count,
                    "japanese_audio_count": jpn_count,
                    "episode_count": show_eps,
                    "timestamp": datetime.now().isoformat()
                }
                logger.info(f"🎧 Updated cached audio counts for '{title}' — ENG: {eng_count}, JPN: {jpn_count}, Episodes: {show_eps}")
            except Exception as e:
                logger.warning(f"⚠️ Audio scan failed for '{title}': {e}")
        else:
            logger.debug(f"🎧 Using cached audio for '{title}' — ENG: {cached_eng}, JPN: {cached_jpn}, Episodes: {show_eps}")

    # ✅ Write audio sub-cache back into main cache
    cache["_audio"] = audio_cache
    save_cache(cache)
    logger.info("✅ Audio cache update complete.\n")

    # ===== PASS 2: FETCH ANILIST INFO & BUILD NORMAL OVERLAYS =====
    for show in library.search(libtype="show"):
        title = show.title
        counters["total"] += 1
        logger.debug(f"Processing: {title}")

        # ---- AniList CACHE SHORT-CIRCUIT ----
        use_cache = (not FORCE_REFRESH and title in cache and is_cache_valid(cache[title], CACHE_EXPIRY_HOURS_ANILIST))
        if use_cache:
            info = cache[title]["result"]
            counters["cache_used"] += 1
            logger.debug(f"📦 Using CACHE for '{title}'")
        else:
            # Real API call
            info, cache = get_next_air_datetime(title, cache, counters, MANUAL_EXCEPTIONS)
            counters["api_calls"] += 1
            #logger.debug(f"⏱️ Rate limit delay: sleeping {RATE_LIMIT_DELAY}s")
            #time.sleep(RATE_LIMIT_DELAY) #uncomment if api rate limiter breaks

        # Get cached audio counts from sub-cache (already computed)
        audio_entry = cache.get("_audio", {}).get(title, {})
        eng_count = audio_entry.get("english_audio_count", 0)
        jpn_count = audio_entry.get("japanese_audio_count", 0)
        # (You can use eng_count/jpn_count later for your audio overlay YAML)

        day, air_str_local = info.get("weekday"), info.get("air_datetime_local")
        if day == "none" or not air_str_local:
            logger.info(f"Skipping {title} (no upcoming episodes).")
            continue

        weekday_overlays[title] = {
            "overlay": {"name": day},
            "plex_search": {"all": {"title": title}}
        }

        try:
            air_dt_local = datetime.strptime(air_str_local, "%Y-%m-%d %H:%M:%S")
            days_until = (air_dt_local.date() - now_local.date()).days

            # Skip if the episode airs too far in the future
            if days_until > MAX_AIR_DAYS:
                logger.info(f"⏩ Skipping '{title}' — next episode airs in {days_until} days (beyond {MAX_AIR_DAYS}-day limit).")
                continue

            label = get_day_label(days_until)
            countdown_overlays[title] = {
                "overlay": {"name": label},
                "plex_search": {"all": {"title": title}}
            }
        except Exception as e:
            logger.warning(f"Failed to calculate day diff for {title}: {e}")
        
        if counters["total"] % 10 == 0:
            save_cache(cache)
            logger.debug("🪣 Partial AniList cache checkpoint saved.")
        
    # ✅ Final cache save to include last processed titles
    logger.info("💾 Finalizing AniList cache...")
    save_cache(cache)
    logger.info("✅ Final AniList cache saved successfully.\n")

    # ===== SAVE OVERLAYS (conditional toggles) =====
    # Writes overlay YAML files only if enabled via environment flags
    try:
        if ENABLE_WEEKDAY_OVERLAY:
            with open(OVERLAY_WEEKDAY_FILE, "w", encoding="utf-8") as f:
                yaml.dump({"overlays": weekday_overlays}, f, sort_keys=False, allow_unicode=True)
            logger.info(f"✅ Weekday overlay file written: {OVERLAY_WEEKDAY_FILE}")
            logger.info(f"🧾 {OVERLAY_WEEKDAY_FILE} MD5: {hash_file(OVERLAY_WEEKDAY_FILE)}")
        else:
            logger.info("🚫 Weekday overlays disabled by config.")

        if ENABLE_COUNTDOWN_OVERLAY:
            with open(OVERLAY_COUNTDOWN_FILE, "w", encoding="utf-8") as f:
                yaml.dump({"overlays": countdown_overlays}, f, sort_keys=False, allow_unicode=True)
            logger.info(f"✅ Countdown overlay file written: {OVERLAY_COUNTDOWN_FILE}")
            logger.info(f"🧾 {OVERLAY_COUNTDOWN_FILE} MD5: {hash_file(OVERLAY_COUNTDOWN_FILE)}")
        else:
            logger.info("🚫 Countdown overlays disabled by config.")

    except Exception as e:
        logger.error(f"❌ Failed to write overlay files: {e}")
    # ===== PASS 3: BUILD AUDIO OVERLAY YAML =====
    if ENABLE_AUDIO_OVERLAY:
        try:
            logger.info("=== 🎧 Building audio overlays ===")
            audio_overlays = {}
            audio_cache = cache.get("_audio", {})

            for title, ainfo in audio_cache.items():
                def limit_two_digits(n):
                    #Cap to 2 digits
                    try:
                        n = int(n)
                        return "99" if n > 99 else str(n)
                    except:
                        return "0"

                def adjust_offset(num_str, base_offset):
                    # Shift right by +20px if it's a single digit.
                    # if "99+" counts as 3+ chars, leave unchanged
                    return base_offset + 20 if len(num_str) == 1 else base_offset

                # 🔧 force integer conversion for safe comparison
                try:
                    raw_eng = int(ainfo.get("english_audio_count", 0))
                    raw_jpn = int(ainfo.get("japanese_audio_count", 0))
                    raw_total = int(ainfo.get("episode_count", 0))
                except Exception:
                    logger.warning(f"⚠️ Invalid audio data for '{title}' — skipping")
                    continue

                # allow zero-episode shows to still display overlay
                if raw_total < 0:
                    continue # only skip truly invalid negative values

                # then format + adjust offset
                eng_audio = limit_two_digits(raw_eng)
                jpn_audio = limit_two_digits(raw_jpn)
                total_eps = limit_two_digits(raw_total)

                offset_jpn = adjust_offset(jpn_audio, 110)
                offset_eng = adjust_offset(eng_audio, 270)
                offset_total = adjust_offset(total_eps, 380)


                # ✅ Template same as your example
                audio_overlays[f"{title} (Base)"] = {
                    "overlay": {"name": "audio_base", "weight": 10},
                    "plex_search": {"all": {"title": title}}
                }

                audio_overlays[f"{title} (JPN)"] = {
                    "overlay": {
                        "name": f"text({jpn_audio})",
                        "weight": 100,
                        "font": "/config/fonts/impact.ttf",
                        "font_size": 80,
                        "font_color": "#FFFFFF",
                        "horizontal_offset": offset_jpn,
                        "vertical_offset": 90,
                        "vertical_align": "top",
                        "horizontal_align": "left",
                    },
                    "plex_search": {"all": {"title": title}},
                }

                audio_overlays[f"{title} (ENG)"] = {
                    "overlay": {
                        "name": f"text({eng_audio})",
                        "weight": 100,
                        "font": "/config/fonts/impact.ttf",
                        "font_size": 80,
                        "font_color": "#FFFFFF",
                        "horizontal_offset": offset_eng,
                        "vertical_offset": 90,
                        "vertical_align": "top",
                        "horizontal_align": "left",
                    },
                    "plex_search": {"all": {"title": title}},
                }

                audio_overlays[f"{title} (Total)"] = {
                    "overlay": {
                        "name": f"text({total_eps})",
                        "weight": 100,
                        "font": "/config/fonts/impact.ttf",
                        "font_size": 80,
                        "font_color": "#FFFFFF",
                        "horizontal_offset": offset_total,
                        "vertical_offset": 90,
                        "vertical_align": "top",
                        "horizontal_align": "left",
                    },
                    "plex_search": {"all": {"title": title}},
                }

            # ===== Write YAML =====
            with open(OVERLAY_AUDIO_FILE, "w", encoding="utf-8") as f:
                yaml.dump({"overlays": audio_overlays}, f, sort_keys=False, allow_unicode=True)
            logger.info(f"✅ Audio overlay file written: {OVERLAY_AUDIO_FILE}")
            logger.info(f"🧾 {OVERLAY_AUDIO_FILE} MD5: {hash_file(OVERLAY_AUDIO_FILE)}")

        except Exception as e:
            logger.error(f"❌ Failed to build audio overlays: {e}")
    else:
        logger.info("🚫 Audio overlays disabled by config.")

    elapsed = time.time() - start_time
    logger.info(f"=== ✅ Overlay Update Complete ({elapsed:.1f}s) ===")
    logger.info(
        f"📊 Summary — Total: {counters['total']} | Cache Used: {counters['cache_used']} | API Calls: {counters['api_calls']} | Airing: {counters['airing_found']} | Skipped: {counters['no_airing']}\n"
    )




# ===== MAIN =====
if __name__ == "__main__":
    print_system_summary()
    build_overlay()
