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
