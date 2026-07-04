# NAS Metadata Platform Wiki

Deze wiki wordt automatisch gegenereerd door de documentatiegenerator.

## Hoofdstukken

- [Architectuur](architecture.md)
- [Scanner](scanner.md)
- [Metadata Worker](metadata-worker.md)
- [Docker](docker.md)
- [PostgreSQL](postgres.md)
- [Redis](redis.md)
- [Scripts](scripts.md)
- [Troubleshooting](troubleshooting.md)
- [Documentatiegenerator](documentation-generator.md)
- [Bronbestanden](sources.md)

## Datastroom

```text
/volume1
  |
  v
Polling Scanner
  |
  v
Redis Stream: scan_stream
  |
  v
Metadata Worker
  |
  v
PostgreSQL

Fouten -> scan_stream_dlq
```
