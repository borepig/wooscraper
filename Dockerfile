FROM python:3.14-slim

# ffmpeg wraps an HLS preview into Preview.mp4. Without it the preview is
# still saved, as a .ts file, beside the video.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LIBRARY_ROOT=/library \
    PORT=5000

EXPOSE 5000
VOLUME ["/library"]

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["serve"]
