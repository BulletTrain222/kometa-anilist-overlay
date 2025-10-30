# kometa-anilist-overlay
Automatically generates Plex poster overlays in Kometa using AniList data — showing next episode air dates, airing weekdays, and more.

'''
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
  '''
  yes
