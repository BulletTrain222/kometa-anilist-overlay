# kometa-anilist-overlay
Automatically generates Plex poster overlays in Kometa using AniList data — showing next episode air dates, airing weekdays, and more.

Minimal Example – Quick Start
```
docker run -d \
  --name=kometa-anilist-overlay \
  -e TZ=America/Los_Angeles `# timezone (optional)` \
  -e PLEX_URL=http://192.168.0.1:32400 `# your plex server URL` \
  -e PLEX_TOKEN=YOUR_PLEX_TOKEN `# your plex token` \
  -e ANILIST_TOKEN=YOUR_ANILIST_TOKEN `# your anilist token` \
  -e LIBRARY_NAME=Anime `# plex library to scan` \
  -e CACHE_EXPIRY_HOURS=120 `# cache refresh rate (hours)` \
  -e RUN_INTERVAL_HOURS=1 `# rerun interval (optional)` \
  -v /path/to/kometa/config:/config `# map your config folder` \
  --restart unless-stopped \
  kometa-anilist-overlay
  ```

Full Example
```
docker run -d \
  --name=kometa-anilist-overlay \
  -e TZ=America/Los_Angeles `# System timezone (optional)` \
  -e PLEX_URL=http://192.168.0.1:32400 `# Plex base URL` \
  -e PLEX_TOKEN=YOUR_PLEX_TOKEN `# Plex authentication token (required)` \
  -e ANILIST_TOKEN=YOUR_ANILIST_TOKEN `# AniList API token (required)` \
  -e LIBRARY_NAME=Anime,TV Shows `# multiple libraries (comma separated)`
  -e OUTPUT_FILE=/config/overlays/next_air_date.yml `# Overlay YAML output path` \
  -e AIRING_DAY_OUTPUT=/config/overlays/airing_day_overlays.yml `# “Days until” overlay YAML output path` \
  -e CACHE_FILE=/config/anilist_cache.json `# JSON cache file path` \
  -e RATE_LIMIT_DELAY=5 `# Seconds between AniList API requests (avoid rate limit)` \
  -e CACHE_EXPIRY_HOURS=120 `# Cache refresh interval (in hours)` \
  -e MAX_AIR_DAYS=14 `# Maximum upcoming days to include` \
  -e FORCE_REFRESH=false `# If true, ignores cache and re-queries AniList` \
  -e ANILIST_DEBUG=false `# Enable detailed debug logging` \
  -e ANILIST_FORMATS=TV,TV_SHORT,ONA,OVA,MOVIE `# Comma-separated formats to include` \
  -e LOG_FILE=/config/logs/anilist_overlay.log `# Path to log file` \
  -e MAX_LOG_SIZE=5242880 `# Maximum log file size before rotation (bytes)` \
  -e BACKUP_COUNT=7 `# Number of old log files to keep` \
  -e RUN_INTERVAL_HOURS=2 `# Re-run overlay generator every X hours` \
  -v /path/to/kometa/config:/config `# Mount your Kometa config directory` \
  --restart unless-stopped \
  kometa-anilist-overlay

  ```
docker-compose.yml
```
version: "3.8"

services:
  kometa-anilist-overlay:
    image: kometa-anilist-overlay
    container_name: kometa-anilist-overlay

    environment:
      TZ: America/Los_Angeles             # Timezone (optional)
      PLEX_URL: http://192.168.0.1:32400  # Plex server URL
      PLEX_TOKEN: YOUR_PLEX_TOKEN         # Plex token (required)
      ANILIST_TOKEN: YOUR_ANILIST_TOKEN   # AniList token (required)
      LIBRARY_NAME: Anime                 # Plex library to scan
      CACHE_EXPIRY_HOURS: 120             # Cache refresh interval (hours)
      RUN_INTERVAL_HOURS: 1               # How often to rerun (hours)

    volumes:
      - /path/to/kometa/config:/config  # Mount your Kometa config directory

    restart: unless-stopped
```

| Variable             | Description                                                                                                                                              | Default                                    |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `PLEX_URL`           | **Base URL of your Plex server.** Used by the script to connect to Plex and read library titles.                                                         | `http://localhost:32400`                   |
| `PLEX_TOKEN`         | **Your Plex authentication token.** Required for API access to your Plex library.                                                                        | **required**                               |
| `ANILIST_TOKEN`      | **AniList personal access token.** Required to query AniList’s GraphQL API for next episode and show data.                                               | **required**                               |
| `LIBRARY_NAME`       | **Name of your Plex library** that contains anime or shows you want processed. Must exactly match the Plex library name.                                 | `Anime`                                    |
| `CACHE_FILE`         | **File path where AniList results are cached.** Prevents re-querying every run and reduces API calls.                                                    | `/config/anilist_cache.json`               |
| `OUTPUT_FILE`        | **File path for next_air_date.yml.** Each show gets an overlay for its *airing weekday* (e.g., `monday`, `friday`).                                      | `/config/overlays/next_air_date.yml`       |
| `AIRING_DAY_OUTPUT`  | **File path for airing_day_overlays.yml.** Generates overlays like `today`, `tomorrow`, `in 3 days`, etc.                                                | `/config/overlays/airing_day_overlays.yml` |
| `RATE_LIMIT_DELAY`   | **Seconds to wait between AniList API calls.** Helps prevent hitting rate limits. Recommended: `3–5`.                                                    | `5`                                        |
| `CACHE_EXPIRY_HOURS` | **How long cached AniList data stays valid** before being refreshed. Lower = more frequent re-queries.                                                   | `24`                                       |
| `ANILIST_FORMATS`    | **Comma-separated AniList formats to include.** Lets you limit to `TV`, `OVA`, etc. Accepted values: `TV`, `TV_SHORT`, `ONA`, `OVA`, `MOVIE`, `SPECIAL`. | `TV,TV_SHORT,ONA,OVA`                      |
| `MAX_AIR_DAYS`       | **Maximum future days to include for airing episodes.** Prevents adding overlays for shows airing months away.                                           | `14`                                       |
| `FORCE_REFRESH`      | **Bypasses cache on next run.** Set `true` to re-fetch all AniList data even if cached. Useful if schedules change.                                      | `false`                                    |
| `ANILIST_DEBUG`      | **Enables detailed AniList match logs.** Logs all candidate titles, synonyms, and match scores_                                                          | `false`                                    |
| `LOG_FILE`           | **File path for log output.** Useful for Docker log persistence.                                                                                         | `/config/logs/anilist_overlay.log`         |
| `MAX_LOG_SIZE`       | **Maximum size (in bytes)** before log rotation. Default = 5 MB (`5 * 1024 * 1024`).                                                                     | `5 * 1024 * 1024`                          |
| `BACKUP_COUNT`       | **Number of rotated log files to keep.** Older logs beyond this count are deleted.                                                                       | `7`                                        |
| `RUN_INTERVAL_HOURS` | How often the container re-runs the overlay update loop. Only used by the Docker entrypoint; ignored if running the script manually.                     | *unset → run once on start*                |


Example airing_day_overlays.yml Result
```
  The Banished Court Magician Aims to Become the Strongest:
    overlay:
      name: in_2_days
    plex_search:
      all:
        title: The Banished Court Magician Aims to Become the Strongest
  Blue Orchestra:
    overlay:
      name: in_3_days
    plex_search:
      all:
        title: Blue Orchestra
  Campfire Cooking in Another World with My Absurd Skill:
    overlay:
      name: in_5_days
    plex_search:
      all:
        title: Campfire Cooking in Another World with My Absurd Skill
  Cat's Eye:
    overlay:
      name: tomorrow
    plex_search:
      all:
        title: Cat's Eye
```
Example next_air_date.yml Result
```
  The Banished Court Magician Aims to Become the Strongest:
    overlay:
      name: saturday
    plex_search:
      all:
        title: The Banished Court Magician Aims to Become the Strongest
  Blue Orchestra:
    overlay:
      name: sunday
    plex_search:
      all:
        title: Blue Orchestra
  Campfire Cooking in Another World with My Absurd Skill:
    overlay:
      name: tuesday
    plex_search:
      all:
        title: Campfire Cooking in Another World with My Absurd Skill
  Cat's Eye:
    overlay:
      name: friday
    plex_search:
      all:
        title: Cat's Eye
```
Example anilist_cache.json Result
```
{
  "Alma-chan Wants to Be a Family!": {             // Each key is a Plex show title as it appears in your library 
    "result": {
      "weekday": "sunday",                         // Local weekday the next episode airs
      "air_datetime_utc": "2025-11-02 14:00:00",   // Airing time in UTC
      "air_datetime_local": "2025-11-02 06:00:00", // Airing time in your system timezone
      "episode_number": 5,                         // Next upcoming episode number
      "time_until_hours": 81.3,                    // Hours remaining until next episode airs (local time)
      "anilist_id": 186190,                        // AniList media ID
      "e": "Alma-chan wa Kazoku ni Naritai",       // Official AniList title used internally
      "match_score": 1.0,                          // Fuzzy match confidence (1.0 = perfect)
      "averageScore": 67,                          // AniList average score (out of 100)
      "matched_synonym": null                      // If matched using an AniList synonym, shows which one
    },
    "timestamp": "2025-10-29T21:41:55.783596"      // When this entry was last refreshed
  },

  "The Banished Court Magician Aims to Become the Strongest": {
    "result": {
      "weekday": "saturday",
      "air_datetime_utc": "2025-11-01 14:30:00",
      "air_datetime_local": "2025-11-01 07:30:00",
      "episode_number": 5,
      "time_until_hours": 57.7,
      "anilist_id": 188487,
      "e": "Mikata ga Yowa Sugite Hojo Mahou ni Toushite Ita Kyuutei Mahoushi, Tsuihou Sarete Saikyou wo Mezasu",
      "match_score": 1.0,
      "averageScore": 60,
      "matched_synonym": null
    },
    "timestamp": "2025-10-29T21:45:00.552291"
  },

  "Blue Orchestra": {
    "result": {
      "weekday": "sunday",
      "air_datetime_utc": "2025-11-02 08:00:00",
      "air_datetime_local": "2025-11-02 01:00:00",
      "episode_number": 5,
      "time_until_hours": 75.2,
      "anilist_id": 170018,
      "e": "Ao no Orchestra Season 2",
      "match_score": 0.683,
      "averageScore": 66,
      "matched_synonym": "The Blue Orchestra Season 2"
    },
    "timestamp": "2025-10-29T21:46:40.595461"
  },

  "Campfire Cooking in Another World with My Absurd Skill": {
    "result": {
      "weekday": "tuesday",
      "air_datetime_utc": "2025-11-04 15:00:00",
      "air_datetime_local": "2025-11-04 07:00:00",
      "episode_number": 5,
      "time_until_hours": 130.2,
      "anilist_id": 170577,
      "e": "Tondemo Skill de Isekai Hourou Meshi 2",
      "match_score": 0.923,
      "averageScore": 75,
      "matched_synonym": null
    },
    "timestamp": "2025-10-29T21:48:00.279226"
  },

  "Cat's Eye": {
    "result": {
      "weekday": "friday",
      "air_datetime_utc": "2025-10-31 07:00:00",
      "air_datetime_local": "2025-10-31 00:00:00",
      "episode_number": 6,
      "time_until_hours": 26.2,
      "anilist_id": 184718,
      "e": "Cat's♥Eye (2025)",
      "match_score": 0.75,
      "averageScore": 57,
      "matched_synonym": "Signé Cat's Eye"
    },
    "timestamp": "2025-10-29T21:48:21.781757"
  },

  "Chitose Is in the Ramune Bottle": {
    "result": {
      "weekday": "tuesday",
      "air_datetime_utc": "2025-11-04 14:00:00",
      "air_datetime_local": "2025-11-04 06:00:00",
      "episode_number": 5,
      "time_until_hours": 129.2,
      "anilist_id": 180082,
      "e": "Chitose-kun wa Ramune Bin no Naka",
      "match_score": 1.0,
      "averageScore": 68,
      "matched_synonym": null
    },
    "timestamp": "2025-10-29T21:49:09.610050"
  }
}

```

<img width="247" height="374" alt="image" src="https://github.com/user-attachments/assets/cadc1930-8b11-40c2-9795-3b287bdbe26d" />
<img width="249" height="374" alt="image" src="https://github.com/user-attachments/assets/9d7b2fef-e89c-40d4-9652-b1d86263d2fd" />
<img width="248" height="373" alt="image" src="https://github.com/user-attachments/assets/550941e8-387e-444d-99da-1b961521df7d" />
<img width="250" height="375" alt="image" src="https://github.com/user-attachments/assets/5c0ecfb7-425d-4722-836c-ee02ec5103d0" />
<img width="248" height="376" alt="image" src="https://github.com/user-attachments/assets/265b643e-2fed-4e7e-b7a1-30840c0a0af9" />
<img width="254" height="376" alt="image" src="https://github.com/user-attachments/assets/f5b526a9-509b-4a7c-a44f-1a230a1078a0" />




