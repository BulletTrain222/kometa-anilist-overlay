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

# ===== CONFIG =====
ANILIST_TOKEN = os.getenv("ANILIST_TOKEN")
PLEX_URL = os.getenv("PLEX_URL", "http://localhost:32400")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
LIBRARY_NAME = os.getenv("LIBRARY_NAME", "Anime")
OUTPUT_FILE = os.getenv("OUTPUT_FILE", "/config/overlays/next_air_date.yml")
AIRING_DAY_OUTPUT = os.getenv("AIRING_DAY_OUTPUT", "/config/overlays/airing_day_overlays.yml")
CACHE_FILE = os.getenv("CACHE_FILE", "/config/anilist_cache.json")

RATE_LIMIT_DELAY = int(os.getenv("RATE_LIMIT_DELAY", 5))
CACHE_EXPIRY_HOURS = int(os.getenv("CACHE_EXPIRY_HOURS", 24))
LOCAL_TZ = pytz.timezone(os.getenv("TZ", "UTC"))
ANILIST_DEBUG = os.getenv("ANILIST_DEBUG", "false").lower() == "true"
MAX_AIR_DAYS = int(os.getenv("MAX_AIR_DAYS", 14))
FORCE_REFRESH = os.getenv("FORCE_REFRESH", "false").lower() == "true"

# ✅ Formats are now configurable (comma-separated in env)
# Example: ANILIST_FORMATS="TV,TV_SHORT,ONA,OVA,MOVIE"
ANILIST_FORMATS = os.getenv("ANILIST_FORMATS", "TV,TV_SHORT,ONA,OVA").split(",")

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


# ===== CACHE HANDLERS =====
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info(f"🗂️  Loaded cache with {len(data)} entries.")
                return data
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info(f"💾 Cache saved successfully ({len(cache)} entries).")
    except Exception as e:
        logger.error(f"Failed to save cache: {e}")

def is_cache_valid(entry):
    try:
        timestamp = datetime.fromisoformat(entry.get("timestamp"))
        return datetime.now() - timestamp < timedelta(hours=CACHE_EXPIRY_HOURS)
    except Exception:
        return False


# ===== PLEX CONNECTION (with retries) =====
def connect_plex(retries=5, delay=10):
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
def get_next_air_datetime(title, cache, counters):
    url = "https://graphql.anilist.co"
    query = f'''
    query ($search: String) {{
      Page(perPage: 10) {{
        media(
          search: $search,
          type: ANIME,
          sort: POPULARITY_DESC,
          format_in: {json.dumps(ANILIST_FORMATS)}
        ) {{
          id
          title {{ romaji english native }}
          synonyms
          format
          status
          averageScore
          nextAiringEpisode {{ airingAt episode }}
        }}
      }}
    }}
    '''
    variables = {"search": title}
    headers = {"Authorization": f"Bearer {ANILIST_TOKEN}"}

    # ✅ Skip cache if FORCE_REFRESH is enabled
    if not FORCE_REFRESH and title in cache and is_cache_valid(cache[title]):
        counters["cache_used"] += 1
        logger.debug(f"♻️ Using cached data for {title}")
        return cache[title]["result"], cache
    elif FORCE_REFRESH:
        logger.info(f"🔄 Force-refreshing AniList data for {title}")

    # 💤 Query AniList
    time.sleep(RATE_LIMIT_DELAY)
    counters["api_calls"] += 1

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

        media_list = data.get("data", {}).get("Page", {}).get("media", [])
        if not media_list:
            logger.debug(f"❌ No AniList matches for {title}")
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        # Debug dump
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

        # 🎯 fuzzy + synonym match
        def similarity(a, b):
            return SequenceMatcher(None, a.lower(), b.lower()).ratio()

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
                if score > best_score:
                    best_match, best_score, matched_synonym = media, score, (candidate if ctype == "synonym" else None)

        if not best_match or best_score < 0.6:
            logger.debug(f"❌ No close AniList match for {title} (best={best_score:.2f})")
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        m = best_match
        airing = m.get("nextAiringEpisode")

        # ✅ Always cache even no-airing matches
        if not airing:
            result.update({
                "anilist_id": m["id"],
                "e": m["title"].get("romaji") or m["title"].get("english") or m["title"].get("native"),
                "match_score": round(best_score, 3),
                "averageScore": m.get("averageScore"),
                "matched_synonym": matched_synonym
            })
            cache[title] = {"result": result, "timestamp": datetime.now().isoformat()}
            return result, cache

        # ✅ Airing show
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
        logger.debug(f"✅ Cached {title} | Next ep: {air_dt_local}")

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


# ===== MAIN OVERLAY BUILDER =====
def build_overlay():
    start_time = time.time()
    logger.info("=== 🚀 Starting AniList → Kometa Overlay Update ===")
    logger.info(f"📦 Library: {LIBRARY_NAME}")
    logger.info(f"🕐 Cache Expiry: {CACHE_EXPIRY_HOURS}h | Rate Limit: {RATE_LIMIT_DELAY}s | Formats: {ANILIST_FORMATS}")
    if FORCE_REFRESH:
        logger.info("♻️ FORCE_REFRESH is ENABLED — cache will be ignored")

    plex = connect_plex()
    library = plex.library.section(LIBRARY_NAME)
    overlays, day_overlays = {}, {}
    cache = load_cache()
    now_local = datetime.now(LOCAL_TZ)
    counters = {"total": 0, "cache_used": 0, "api_calls": 0, "airing_found": 0, "no_airing": 0}

    for show in library.search(libtype="show"):
        title = show.title
        counters["total"] += 1
        logger.debug(f"Processing: {title}")
        info, cache = get_next_air_datetime(title, cache, counters)
        day, air_str_local = info.get("weekday"), info.get("air_datetime_local")
        if day == "none" or not air_str_local:
            logger.debug(f"Skipping {title} (no upcoming episodes).")
            continue

        overlays[title] = {"overlay": {"name": day}, "plex_search": {"all": {"title": title}}}
        try:
            air_dt_local = datetime.strptime(air_str_local, "%Y-%m-%d %H:%M:%S")
            days_until = (air_dt_local.date() - now_local.date()).days
            label = get_day_label(days_until)
            day_overlays[title] = {"overlay": {"name": label}, "plex_search": {"all": {"title": title}}}
        except Exception as e:
            logger.warning(f"Failed to calculate day diff for {title}: {e}")

    save_cache(cache)

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            yaml.dump({"overlays": overlays}, f, sort_keys=False, allow_unicode=True)
        with open(AIRING_DAY_OUTPUT, "w", encoding="utf-8") as f:
            yaml.dump({"overlays": day_overlays}, f, sort_keys=False, allow_unicode=True)
        logger.info(f"✅ Overlay file written: {OUTPUT_FILE}")
        logger.info(f"✅ Airing-day overlay file written: {AIRING_DAY_OUTPUT}")
    except Exception as e:
        logger.error(f"Failed to write overlay files: {e}")

    elapsed = time.time() - start_time
    logger.info(f"=== ✅ Overlay Update Complete ({elapsed:.1f}s) ===")
    logger.info(f"📊 Summary — Total: {counters['total']} | Cache Used: {counters['cache_used']} | API Calls: {counters['api_calls']} | Airing: {counters['airing_found']} | No Airing: {counters['no_airing']}\n")


# ===== MAIN =====
if __name__ == "__main__":
    build_overlay()
