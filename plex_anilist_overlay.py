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

# ===== CONFIG =====
ANILIST_TOKEN = os.getenv("ANILIST_TOKEN")
PLEX_URL = os.getenv("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
LIBRARY_NAME = os.getenv("LIBRARY_NAME", "Anime")
# File output locations
OVERLAY_WEEKDAY_FILE = os.getenv("OVERLAY_WEEKDAY_FILE", "/config/overlays/weekday_overlays.yml")
OVERLAY_COUNTDOWN_FILE = os.getenv("OVERLAY_COUNTDOWN_FILE", "/config/overlays/countdown_overlays.yml")
CACHE_FILE = os.getenv("CACHE_FILE", "/config/anilist_cache.json")
MANUAL_EXCEPTIONS_FILE = os.getenv("MANUAL_EXCEPTIONS_FILE", "/config/manual_exceptions.json")
# Behavioral and timing settings
RATE_LIMIT_DELAY = int(os.getenv("RATE_LIMIT_DELAY", 5))
CACHE_EXPIRY_HOURS = int(os.getenv("CACHE_EXPIRY_HOURS", 24))
LOCAL_TZ = pytz.timezone(os.getenv("TZ", "UTC"))
ANILIST_DEBUG = os.getenv("ANILIST_DEBUG", "false").lower() == "true"
MAX_AIR_DAYS = int(os.getenv("MAX_AIR_DAYS", 14))
FORCE_REFRESH = os.getenv("FORCE_REFRESH", "false").lower() == "true"
CLEAN_MISSING_FROM_PLEX = os.getenv("CLEAN_MISSING_FROM_PLEX", "false").lower() == "true"

# ===== LOGGING =====
LOG_FILE = os.getenv("LOG_FILE", "/config/logs/anilist_overlay.log")
MAX_LOG_SIZE = int(os.getenv("MAX_LOG_SIZE", 5 * 1024 * 1024))
BACKUP_COUNT = int(os.getenv("BACKUP_COUNT", 7))

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)# Ensure log folder exists; create it if missing
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
        with open(CACHE_FILE, "w", encoding="utf-8") as f: # Open cache file in write mode
            json.dump(cache, f, ensure_ascii=False, indent=2) # Save cache as pretty-printed JSON
        logger.info(f"💾 Cache saved successfully ({len(cache)} entries).") # Confirm save success
        logger.info(f"🧾 {CACHE_FILE} MD5: {hash_file(CACHE_FILE)}")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def is_cache_valid(entry):
    try:
        ts_str = entry.get("timestamp")
        if not ts_str: # No timestamp = invalid
            return False

        ts = datetime.fromisoformat(ts_str)
        now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.now()

        # Normal time-based cache expiry
        if (now - ts) >= timedelta(hours=CACHE_EXPIRY_HOURS):
            return False

        # --- NEW: Invalidate cache if the stored air date already passed ---
        result = entry.get("result", {})
        air_local_str = result.get("air_datetime_local")
        if air_local_str: # If an air date exists, check if it's outdated
            try:
                air_local = datetime.strptime(air_local_str, "%Y-%m-%d %H:%M:%S")
                if now.date() > air_local.date(): # Only invalidate *after midnight* of the air date
                    return False #It's a new day → invalidate
            except Exception:
                pass  # ignore if malformed

        return True # Cache is still valid
    except Exception:
        return False # On any error, assume cache invalid


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
        response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
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

    for show in library.search(libtype="show"):
        title = show.title
        counters["total"] += 1
        logger.debug(f"Processing: {title}")
        info, cache = get_next_air_datetime(title, cache, counters, MANUAL_EXCEPTIONS)
        day, air_str_local = info.get("weekday"), info.get("air_datetime_local")
        if day == "none" or not air_str_local:
            logger.info(f"Skipping {title} (no upcoming episodes).")
            continue

        weekday_overlays[title] = {"overlay": {"name": day}, "plex_search": {"all": {"title": title}}}
        try:
            air_dt_local = datetime.strptime(air_str_local, "%Y-%m-%d %H:%M:%S")
            days_until = (air_dt_local.date() - now_local.date()).days
            label = get_day_label(days_until)
            countdown_overlays[title] = {"overlay": {"name": label}, "plex_search": {"all": {"title": title}}}
        except Exception as e:
            logger.warning(f"Failed to calculate day diff for {title}: {e}")
    # ===== CLEAN DEAD CACHE ENTRIES =====
    if CLEAN_MISSING_FROM_PLEX:
        logger.info("🧹 Checking for cache entries no longer present in Plex library...")
        plex_titles = {show.title for show in library.search(libtype="show")}
        before_count = len(cache)
        removed_entries = []

        for title in list(cache.keys()):
            if title not in plex_titles:
                entry = cache.get(title, {})
                ts = entry.get("timestamp")
                age_days = None
                if ts:
                    try:
                        age_days = (datetime.now() - datetime.fromisoformat(ts)).days
                    except Exception:
                        pass
                removed_entries.append((title, age_days))
                del cache[title]

        removed = len(removed_entries)
        if removed > 0:
            for title, age in removed_entries:
                if age is not None:
                    logger.debug(f"🗑️ Removed '{title}' (cache age: {age} days)")
                else:
                    logger.debug(f"🗑️ Removed '{title}' (no timestamp found)")
            logger.info(f"🧽 Cleaned {removed} cache entr{'y' if removed == 1 else 'ies'} missing from Plex library.")
        else:
            logger.info("🧼 No missing Plex entries found in cache.")
    else:
        logger.debug("🧩 Cache cleanup skipped (CLEAN_MISSING_FROM_PLEX=false).")


    save_cache(cache)

    try:
        with open(OVERLAY_WEEKDAY_FILE, "w", encoding="utf-8") as f:
            yaml.dump({"overlays": weekday_overlays}, f, sort_keys=False, allow_unicode=True)
        with open(OVERLAY_COUNTDOWN_FILE, "w", encoding="utf-8") as f:
            yaml.dump({"overlays": countdown_overlays}, f, sort_keys=False, allow_unicode=True)
        logger.info(f"✅ Weekday overlay file written: {OVERLAY_WEEKDAY_FILE}")
        logger.info(f"✅ Countdown overlay file written: {OVERLAY_COUNTDOWN_FILE}")
        logger.info(f"🧾 {OVERLAY_WEEKDAY_FILE} MD5: {hash_file(OVERLAY_WEEKDAY_FILE)}")
        logger.info(f"🧾 {OVERLAY_COUNTDOWN_FILE} MD5: {hash_file(OVERLAY_COUNTDOWN_FILE)}")
    except Exception as e:
        logger.error(f"Failed to write overlay files: {e}")

    elapsed = time.time() - start_time
    logger.info(f"=== ✅ Overlay Update Complete ({elapsed:.1f}s) ===")
    logger.info(f"📊 Summary — Total: {counters['total']} | Cache Used: {counters['cache_used']} | API Calls: {counters['api_calls']} | Airing: {counters['airing_found']} | Skipped: {counters['no_airing']}\n")

# ===== MAIN =====
if __name__ == "__main__":
    print_system_summary()
    build_overlay()

