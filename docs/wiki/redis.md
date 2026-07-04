# Redis

Redis is de event- en statuslaag.

## Belangrijke keys

- `scan_stream`
- `scan_stream_dlq`
- `metadata_group`
- `scanner:lock:event`
- `metadata_worker:lock`
- heartbeat keys

## Checks

```bash
docker exec -it nas-redis-1 redis-cli XLEN scan_stream
docker exec -it nas-redis-1 redis-cli XINFO GROUPS scan_stream
docker exec -it nas-redis-1 redis-cli XINFO CONSUMERS scan_stream metadata_group
docker exec -it nas-redis-1 redis-cli XLEN scan_stream_dlq
```
