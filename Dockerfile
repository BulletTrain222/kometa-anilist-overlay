FROM python:3.12-slim
WORKDIR /app

COPY plex_anilist_overlay.py .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

VOLUME ["/config"]

# Default timezone and run interval (can be overridden with -e)
ENV TZ=America/Los_Angeles
ENV RUN_INTERVAL_HOURS=24

# Add the run loop script
COPY run_loop.sh /app/run_loop.sh
RUN chmod +x /app/run_loop.sh

# Start the loop instead of running Python directly
CMD ["/app/run_loop.sh"]
