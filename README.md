# kometa-anilist-overlay
Automatically generates Plex poster overlays in Kometa using AniList data — showing next episode air dates, airing weekdays, and more.

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

  
| Variable             | Description                                      | Default                                    |
| -------------------- | ------------------------------------------------ | ------------------------------------------ |
| `PLEX_URL`           | Your Plex server base URL                        | `http://localhost:32400`                   |
| `PLEX_TOKEN`         | Plex authentication token                        | **required**                               |
| `ANILIST_TOKEN`      | AniList API token                                | **required**                               |
| `LIBRARY_NAME`       | Plex library name to process                     | `Anime`                                    |
| `CACHE_FILE`         | Path for cache JSON                              | `/config/anilist_cache.json`               |
| `OUTPUT_FILE`        | Overlay YAML output file                         | `/config/overlays/next_air_date.yml`       |
| `AIRING_DAY_OUTPUT`  | “Days until” overlay YAML file                   | `/config/overlays/airing_day_overlays.yml` |
| `RATE_LIMIT_DELAY`   | Seconds between AniList API calls                | `5`                                        |
| `CACHE_EXPIRY_HOURS` | Cache lifetime before re-query                   | `24`                                       |
| `ANILIST_FORMATS`    | Comma-separated formats (TV, ONA, OVA, etc.)     | `TV,TV_SHORT,ONA,OVA`                      |
| `MAX_AIR_DAYS`       | Ignore shows airing more than this many days out | `14`                                       |
| `FORCE_REFRESH`      | `true` = ignore cache on next run                | `false`                                    |
| `ANILIST_DEBUG`      | Enable detailed AniList match logging            | `false`                                    |
| `TZ`                 | System timezone                                  | `UTC`                                      |

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




