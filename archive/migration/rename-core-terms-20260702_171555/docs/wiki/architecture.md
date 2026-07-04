# Architectuur

De NAS Metadata Stack bestaat uit een polling scanner, Redis Streams, een metadata worker en PostgreSQL.

## Ontwerpkeuzes

- Geen host watcher meer.
- Geen inotify-afhankelijkheid.
- Scanner draait in Docker.
- Redis Streams koppelen scanner en worker los van elkaar.
- Consumer Groups maken gecontroleerde verwerking mogelijk.
- PostgreSQL bewaart de permanente metadata-index.
- Heartbeats en locks voorkomen dubbele processen.
- DLQ voorkomt dat slechte events de worker blokkeren.
