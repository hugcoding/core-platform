"""Configuration-driven, deterministic portal review options."""

from __future__ import annotations

import json
import hashlib
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from collections import Counter


@lru_cache(maxsize=1)
def taxonomy() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("document_taxonomy_v1.json").read_text(encoding="utf-8"))


def category_label(code: str) -> str:
    return next((item["label"] for item in taxonomy()["categories"] if item["code"] == code), code)


def family_label(code: str) -> str:
    return next((item["label"] for item in taxonomy()["families"] if item["code"] == code), code)


def normalize_taxonomy_label(value: str) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def taxonomy_extension_code(label: str) -> str:
    ascii_label = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", ascii_label.casefold()).strip("_")[:64]
    if not base:
        base = "voorstel"
    digest = hashlib.sha256(normalize_taxonomy_label(label).encode()).hexdigest()[:8]
    return "custom_{}_{}".format(base, digest)


def extend_taxonomy(base: dict[str, Any], extensions: list[dict[str, Any]]) -> dict[str, Any]:
    result = json.loads(json.dumps(base))
    category_codes = {item["code"] for item in result["categories"]}
    family_keys = {(item["code"], tuple(item.get("categories", []))) for item in result["families"]}
    for item in extensions:
        if item.get("proposal_type") == "category":
            if item["taxonomy_code"] not in category_codes:
                result["categories"].append({"code": item["taxonomy_code"], "label": item["proposed_label"]})
                category_codes.add(item["taxonomy_code"])
        elif item.get("proposal_type") == "family" and item.get("category_code"):
            key = (item["taxonomy_code"], (item["category_code"],))
            if key not in family_keys:
                result["families"].append({
                    "code": item["taxonomy_code"], "label": item["proposed_label"],
                    "categories": [item["category_code"]], "keywords": [],
                    "source": "accepted_human_taxonomy_extension",
                })
                family_keys.add(key)
    if extensions:
        result["version"] = "{}+db".format(base["version"])
    return result


def build_taxonomy_proposals(
    reviews: list[dict[str, Any]], decisions: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    base_taxonomy = taxonomy()
    existing_labels = {
        "category": {
            normalize_taxonomy_label(item["label"])
            for item in base_taxonomy["categories"]
        },
        "family": {
            normalize_taxonomy_label(item["label"])
            for item in base_taxonomy["families"]
        },
    }
    latest_by_file: dict[int, dict[str, Any]] = {}
    for row in reviews:
        if row.get("review_type") == "target_path":
            latest_by_file[int(row["file_id"])] = row
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    labels: dict[tuple[str, str, str], str] = {}
    for row in latest_by_file.values():
        if row.get("decision") != "accepted":
            continue
        for proposal_type, field in (("category", "proposed_category_label"), ("family", "proposed_family_label")):
            label = str(row.get(field) or "").strip()
            if not label:
                continue
            # A human may type the visible label of an existing option in the
            # free-form proposal field. That is evidence for the existing
            # taxonomy, not a request to create a duplicate custom option.
            if normalize_taxonomy_label(label) in existing_labels[proposal_type]:
                continue
            category = "" if proposal_type == "category" else str(row.get("corrected_category_code") or "")
            if proposal_type == "family" and not category:
                continue
            key = (proposal_type, category, normalize_taxonomy_label(label))
            grouped.setdefault(key, []).append(row)
            labels.setdefault(key, label)
    latest_decisions = {str(item["proposal_key"]): item for item in decisions or []}
    result = []
    for (proposal_type, category, normalized), evidence in grouped.items():
        proposal_key = "{}:{}:{}".format(proposal_type, category, normalized)
        decision = latest_decisions.get(proposal_key, {})
        result.append({
            "proposal_key": proposal_key, "proposal_type": proposal_type,
            "category_code": category or None, "proposed_label": labels[(proposal_type, category, normalized)],
            "normalized_label": normalized, "taxonomy_code": taxonomy_extension_code(labels[(proposal_type, category, normalized)]),
            "support": len(evidence), "example_file_ids": sorted(int(item["file_id"]) for item in evidence)[:10],
            "source_review_event_ids": sorted(str(item["id"]) for item in evidence)[:20],
            "decision": decision.get("decision") or "pending",
            "decision_at": decision.get("created_at"), "reviewer": decision.get("reviewer"),
        })
    return sorted(result, key=lambda item: (item["decision"] != "pending", -item["support"], item["proposed_label"].casefold()))


CATEGORY_SIGNALS = {
    "work_career": ("/werk/", "sollicit", "vacature", "cv & sollicitaties", "contractvoorstel", "werkgever"),
    "home_living": ("/wonen/", "/vve ", "/vve/", "woning", "hypotheek", "eksterlaan", "riolering", "onderhoud"),
    "finance": ("/geldzaken/", "belasting", "factuur", "bank", "toeslag", "salaris"),
    "health": ("/gezondheid/", "medisch", "huisarts", "ziekenhuis", "zorg"),
    "family_relationships": ("/gezin", "familie", "relatie"),
    "learning_development": ("/studie/", "/opleiding/", "cursus", "certificaat", "diploma"),
    "identity_personal": ("/persoonlijk/", "paspoort", "rijbewijs", "geboorteakte", "identiteit"),
    "legal": ("/juridisch/", "bezwaar", "beroep", "rechtbank", "advocaat"),
}


def category_options(
    row: dict[str, Any],
    proposal: dict[str, Any],
    maximum: int = 4,
) -> list[dict[str, Any]]:
    """Rank categories using direct signals and family keyword evidence."""

    evidence = (
        "/"
        + " ".join(
            str(row.get(key) or "")
            for key in ("path", "filename")
        )
        .replace("\\", "/")
        .casefold()
    )

    current = str(proposal.get("category_code") or "")

    categories = [
        item
        for item in taxonomy()["categories"]
        if item["code"] != "needs_review"
    ]

    scores: list[tuple[int, int, dict[str, Any]]] = []

    for order, item in enumerate(categories):
        score = 0
        reasons: list[str] = []

        # 1. Bestaande directe categorie-signalen.
        direct_hits = [
            signal
            for signal in CATEGORY_SIGNALS.get(item["code"], ())
            if signal in evidence
        ]

        if direct_hits:
            score += len(direct_hits) * 20
            reasons.append("path_or_filename_signal")

        # 2. Keywords van families die bij deze categorie horen.
        family_hits: list[dict[str, Any]] = []

        for family in taxonomy()["families"]:
            if item["code"] not in family.get("categories", []):
                continue

            hits = [
                keyword
                for keyword in family.get("keywords", [])
                if str(keyword).casefold() in evidence
            ]

            if not hits:
                continue

            family_hits.append({
                "family_code": family["code"],
                "hits": hits,
            })

            # Een family-keyword is sterker bewijs dan een
            # algemeen categorie-signaal.
            score += 40 + (len(hits) * 10)

        if family_hits:
            reasons.append("family_keyword_match")

        # 3. Het bestaande CORE-voorstel blijft zwaar meewegen.
        if current == item["code"]:
            score += 100
            reasons.insert(0, "current_core_proposal")

        if not score:
            continue

        if score >= 100:
            confidence = "high"
        elif score >= 50:
            confidence = "medium"
        else:
            confidence = "low"

        scores.append((
            score,
            -order,
            {
                **item,
                "reason_codes": reasons,
                "confidence": confidence,
                "family_evidence": family_hits,
            },
        ))

    ranked = [
        item
        for _, _, item
        in sorted(scores, reverse=True)
    ]

    # Vul de lijst aan met alternatieven zodat de UI bruikbaar blijft.
    for item in categories:
        if len(ranked) >= maximum:
            break

        if not any(
            candidate["code"] == item["code"]
            for candidate in ranked
        ):
            ranked.append({
                **item,
                "reason_codes": ["alternative"],
                "confidence": "low",
                "family_evidence": [],
            })

    return ranked[:maximum]

def taxonomy_fallback_proposal(
    row: dict[str, Any],
    proposal: dict[str, Any],
) -> dict[str, Any] | None:
    """Suggest category + family when CORE has no reliable classification."""
    current_category = str(proposal.get("category_code") or "")

    if current_category and current_category != "needs_review":
        return None

    evidence = " ".join(
        str(row.get(key) or "")
        for key in ("filename", "path", "document_family")
    ).casefold()

    matches: list[tuple[int, int, dict[str, Any], list[str]]] = []

    for order, family in enumerate(taxonomy()["families"]):
        if family["code"] == "general":
            continue

        hits = [
            keyword
            for keyword in family.get("keywords", [])
            if keyword.casefold() in evidence
        ]

        if not hits:
            continue

        # Longer/multiple matching keywords provide stronger evidence.
        score = (
            len(hits) * 100
            + max(len(keyword) for keyword in hits)
        )

        matches.append((score, -order, family, hits))

    if not matches:
        return None

    matches.sort(reverse=True, key=lambda item: (item[0], item[1]))

    best_score, _, family, hits = matches[0]

    # Do not guess between multiple categories without additional evidence.
    categories = family.get("categories", [])

    if len(categories) != 1:
        category_scores: Counter[str] = Counter()

        path_evidence = "/" + str(row.get("path") or "").replace("\\", "/").casefold()

        for category in categories:
            for signal in CATEGORY_SIGNALS.get(category, ()):
                if signal in path_evidence:
                    category_scores[category] += 1

        if category_scores:
            category = category_scores.most_common(1)[0][0]
        else:
            # Taxonomy order is the deterministic fallback.
            category = categories[0]
    else:
        category = categories[0]

    return {
        "category_code": category,
        "document_family_code": family["code"],
        "family_label": family["label"],
        "matched_keywords": hits,
        "score": best_score,
        "confidence": "high" if len(hits) >= 2 else "medium",
        "reason_code": "taxonomy_keyword_fallback",
    }

def contextual_options(row: dict[str, Any], proposal: dict[str, Any], maximum: int = 5) -> dict[str, Any]:
    """Return a small explained family shortlist plus the full searchable contract."""
    evidence = " ".join(str(row.get(key) or "") for key in ("filename", "path", "document_family")).casefold()
    category = str(proposal.get("category_code") or "needs_review")
    current = str(proposal.get("document_family_code") or "general")
    scored = []
    for order, family in enumerate(taxonomy()["families"]):
        score, reasons = 0, []
        if family["code"] == current:
            score += 100
            reasons.append("current_core_proposal")
        if category in family["categories"]:
            score += 20
            reasons.append("same_category")
        hits = [keyword for keyword in family.get("keywords", []) if keyword in evidence]
        if hits:
            score += 50 + len(hits)
            reasons.append("keyword_match")
        if score:
            scored.append((score, -order, {**family, "reason_codes": reasons}))
    compact = [item for _, _, item in sorted(scored, reverse=True)[:maximum]]
    return {
        "taxonomy_version": taxonomy()["version"],
        "categories": taxonomy()["categories"],
        "category_options": category_options(row, proposal),
        "compact_families": compact,
        "all_families": taxonomy()["families"],
        "maximum_compact_options": maximum,
        "selection_method": "deterministic_context_v1",
    }
