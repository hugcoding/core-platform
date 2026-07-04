# Troubleshooting

## Worker is unhealthy

```bash
docker inspect nas-metadata_worker-1 --format '{{json .State.Health}}'
```

Controleer of de healthcheck `python3` gebruikt.

## Scanner doet niets

```bash
./logs
./status
```

## Worker zegt dat er al een worker draait

Controleer locks en heartbeats:

```bash
./status
```

## DLQ groeit

```bash
./dlq
```

## Noodoplossing locks

```bash
./cleanlocks
```
