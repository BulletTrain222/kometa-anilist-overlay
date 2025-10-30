# kometa-anilist-overlay
Automatically generates Plex poster overlays in Kometa using AniList data — showing next episode air dates, airing weekdays, and more.

Docker Run Example
```
docker run -d \
  --name=kometa-anilist-overlay \
  -e TZ=America/Los_Angeles `# timezone (optional)` \
  -e PLEX_URL=http://192.168.0.1:32400 `# your plex server URL` \
  -e PLEX_TOKEN=YOUR_PLEX_TOKEN `# your plex token` \
  -e ANILIST_TOKEN=YOUR_ANILIST_TOKEN `# your anilist token` \
  -e RATE_LIMIT_DELAY=5 `# seconds between anilist API calls` \
  -e CACHE_EXPIRY_HOURS=120 `# cache refresh rate (hours)` \
  -e LIBRARY_NAME=Anime `# plex library to scan` \
  -e LOG_FILE=/config/logs/overlay.log `# log output file path` \
  -e RUN_INTERVAL_HOURS=1 `# rerun interval (optional)` \
  -e MAX_AIR_DAYS=14 `# max upcoming days to include` \
  -e ANILIST_DEBUG=true `# enable detailed debug logs` \
  -e ANILIST_FORMATS=TV,TV_SHORT,ONA,OVA `# media formats to include` \
  -e FORCE_REFRESH=false `# ignore cache and force API refresh` \
  -v /path/to/kometa/config:/config `# map your config folder` \
  --restart unless-stopped \
  kometa-anilist-overlay
  ```

  
| Variable             | Description                                                                                                                                              | Default                                    |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `PLEX_URL`           | **Base URL of your Plex server.** Used by the script to connect to Plex and read library titles.                                                         | `http://localhost:32400`                   |
| `PLEX_TOKEN`         | **Your Plex authentication token.** Required for API access to your Plex library.                                                                        | **required**                               |
| `ANILIST_TOKEN`      | **AniList personal access token.** Required to query AniList’s GraphQL API for next episode and show data.                                               | **required**                               |
| `LIBRARY_NAME`       | **Name of your Plex library** that contains anime or shows you want processed. Must exactly match the Plex library name.                                 | `Anime`                                    |
| `CACHE_FILE`         | **Path where AniList results are cached.** Prevents re-querying every run and reduces API calls.                                                         | `/config/anilist_cache.json`               |
| `OUTPUT_FILE`        | **Path for next_air_date.yml.** Each show gets an overlay for its *airing weekday* (e.g., `monday`, `friday`).                                           | `/config/overlays/next_air_date.yml`       |
| `AIRING_DAY_OUTPUT`  | **Path for airing_day_overlays.yml.** Generates overlays like `today`, `tomorrow`, `in 3 days`, etc.                                                     | `/config/overlays/airing_day_overlays.yml` |
| `RATE_LIMIT_DELAY`   | **Seconds to wait between AniList API calls.** Helps prevent hitting rate limits. Recommended: `3–5`.                                                    | `5`                                        |
| `CACHE_EXPIRY_HOURS` | **How long cached AniList data stays valid** before being refreshed. Lower = more frequent re-queries.                                                   | `24`                                       |
| `ANILIST_FORMATS`    | **Comma-separated AniList formats to include.** Lets you limit to `TV`, `OVA`, etc. Accepted values: `TV`, `TV_SHORT`, `ONA`, `OVA`, `MOVIE`, `SPECIAL`. | `TV,TV_SHORT,ONA,OVA`                      |
| `MAX_AIR_DAYS`       | **Maximum future days to include for airing episodes.** Prevents adding overlays for shows airing months away.                                           | `14`                                       |
| `FORCE_REFRESH`      | **Bypasses cache on next run.** Set `true` to re-fetch all AniList data even if cached. Useful if schedules change.                                      | `false`                                    |
| `ANILIST_DEBUG`      | **Enables detailed AniList match logs.** Logs all candidate titles, synonyms, and match scores_                                                          | `false`                                    |

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
<img width="247" height="374" alt="image" src="https://github.com/user-attachments/assets/cadc1930-8b11-40c2-9795-3b287bdbe26d" />
<img width="249" height="374" alt="image" src="https://github.com/user-attachments/assets/9d7b2fef-e89c-40d4-9652-b1d86263d2fd" />
<img width="248" height="373" alt="image" src="https://github.com/user-attachments/assets/550941e8-387e-444d-99da-1b961521df7d" />
<img width="250" height="375" alt="image" src="https://github.com/user-attachments/assets/5c0ecfb7-425d-4722-836c-ee02ec5103d0" />
<img width="248" height="376" alt="image" src="https://github.com/user-attachments/assets/265b643e-2fed-4e7e-b7a1-30840c0a0af9" />
<img width="254" height="376" alt="image" src="https://github.com/user-attachments/assets/f5b526a9-509b-4a7c-a44f-1a230a1078a0" />




