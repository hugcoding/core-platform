# Lokale capacity-aanpassing opnemen in Git

De bestaande lokale wijziging in core/runtime/capacity.py verhoogt de Python-
standaard voor Finance en OCR van 60% naar 70%. De standaard hervatgrens zonder
expliciete configuratie verschuift daarmee van 50% naar 60%. AI blijft 70/60 en
gecontroleerde uitvoering 80/70. De centrale meetmethode, tijdvensters en
beveiligingen veranderen niet.

Dit zijn Python-fallbacks. Expliciete CORE_*_MAX_CPU_PERCENT en
CORE_*_CPU_RESUME_PERCENT blijven leidend. De bestaande Compose-defaults voor
Finance/OCR blijven 60/50; deze PR verandert geen lokale .env, secrets, Compose-
configuratie of actieve containers. Voor deze Git-opruiming is geen rebuild nodig.

De patch is apart gecommit en gepusht; alleen deze lokale wijziging wordt ook
met een benoemde stash bewaard. Ongetrackte bestanden blijven ongemoeid.
Hierdoor blokkeert de patch de eerstvolgende pull niet meer.

## Gebruik op de NAS

Merge de PR in GitHub. Voer daarna uit:

```bash
cd /volume1/docker/nas-stack
core git status --short
core git pull --skip-docs
```

Zet de bewaarde capacity-stash niet opnieuw terug nadat deze PR is gemerged:
dezelfde wijziging staat dan in main. De stash blijft als extra reserve bestaan;
er wordt geen stash verwijderd. Als er andere bijgehouden wijzigingen zijn,
moeten die eerst afzonderlijk worden bewaard of gecommit.

Tests controleren de fallbackwaarden, runtime-overrides, hysterese en centrale
CPU-toelating. Geen productie-pull, merge of deployment uitgevoerd.
