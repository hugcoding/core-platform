# Docker

## Services

- `redis`
- `scanner`
- `metadata_worker`
- `redis_data`

## Environment variables

- `DB_HOST`
- `DB_NAME`
- `DB_PASS`
- `DB_PORT`
- `DB_USER`
- `FORCE_FULL_METADATA`
- `REDIS_HOST`
- `SCAN_ROOT`

## docker-compose.yml

```yaml
name: nas
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes", "--maxmemory-policy", "noeviction"]
    volumes: [redis_data:/data]
    healthcheck: { test: ["CMD", "redis-cli", "ping"], interval: 10s, timeout: 5s, retries: 3 }

  scanner:
    build: { context: ., dockerfile: Dockerfile.scanner }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - DB_HOST=${DB_HOST}
      - REDIS_HOST=redis
      - SCAN_ROOT=${SCAN_ROOT:-/volume1}

  metadata_worker:
    build: { context: ., dockerfile: Dockerfile.metadata }
    restart: unless-stopped
    depends_on: { redis: { condition: service_healthy } }
    volumes: ["/volume1:/volume1:ro"]
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT}
      - DB_USER=${DB_USER}
      - DB_PASS=${DB_PASS}
      - DB_NAME=${DB_NAME}
      - REDIS_HOST=redis
      - FORCE_FULL_METADATA=${FORCE_FULL_METADATA:-false}

    healthcheck:
      test: ["CMD", "python3", "-c", "import redis; r=redis.Redis(host='redis', decode_responses=True); r.ping()"]
      interval: 30s
      timeout: 5s
      retries: 3

volumes:
  redis_data:
```

## Dockerfile.base

```dockerfile
FROM debian:bookworm-slim

ENV TZ=Europe/Amsterdam
ENV DEBIAN_FRONTEND=noninteractive

# OS dependencies (inotify + ffprobe zijn hier al inbegrepen)
RUN apt-get update && apt-get install -y \
    curl wget ca-certificates bash tzdata \
    python3 python3-pip \
    libmagic1 libvips42 ffmpeg inotify-tools \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip3 install --break-system-packages redis psycopg2-binary xxhash python-magic pyvips

WORKDIR /app
```

## Dockerfile.scanner

```dockerfile
FROM nas-base:v1
WORKDIR /app
COPY scanner.py .
CMD ["python3", "scanner.py"]
```

## Dockerfile.metadata

```dockerfile
FROM nas-base:v1
WORKDIR /app
COPY metadata_worker.py .
CMD ["python3", "metadata_worker.py"]
```
