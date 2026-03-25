#!/usr/bin/env python3
"""Discover new AI4DB researchers from recent OpenAlex works.

The script scans recent works for AI4DB-related signals, matches affiliations
against a QS-top-100 cache, and then:

1. appends new researchers when the institution matches a QS<100 university,
   even if that school is not already present in ``data/institutions.json``;
2. updates existing researchers by adding missing notable papers.

It is intentionally conservative: papers need both a topical signal and a QS
match, and auto-discovered schools get explicit display metadata so the
dashboard can render them even when the institution registry has no entry yet.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils import load_institutions, load_researchers, next_id, save_researchers

OPENALEX_WORKS_API = "https://api.openalex.org/works"
DEFAULT_LOOKBACK_DAYS = 21
DEFAULT_PAGE_SIZE = 200
MAX_PAGES_PER_QUERY = 3
QS_RANKINGS_PATH = ROOT_DIR / "data" / "qs_rankings.json"

# High-signal terms for AI4DB / database + LLM discovery.
SEARCH_TERMS = [
    "text-to-sql",
    "nl2sql",
    "semantic parsing",
    "schema linking",
    "table question answering",
    "data agents",
    "query optimization",
    "query processing",
    "knowledge graph",
    "graph database",
    "retrieval augmented generation",
    "database systems",
    "data management",
    "llm database",
]

# Venue markers used to keep only DB-top-conference / arXiv works.
VENUE_MARKERS = [
    "sigmod",
    "vldb",
    "icde",
    "pods",
    "edbt",
    "cidr",
    "arxiv",
]

# Keyword -> controlled tag mapping.
KEYWORD_PATTERNS = [
    (r"\btext[- ]?to[- ]?sql\b", "text-to-SQL"),
    (r"\bnl2sql\b", "NL2SQL"),
    (r"\bsemantic parsing\b", "NL2SQL"),
    (r"\bschema linking\b", "schema-linking"),
    (r"\btable (question answering|qa)\b", "table-QA"),
    (r"\bdata agents?\b", "data-agents"),
    (r"\bquery optimization\b", "query-optimization"),
    (r"\bquery processing\b", "query-optimization"),
    (r"\bknowledge graphs?\b", "knowledge-graph"),
    (r"\bgraph databases?\b", "knowledge-graph"),
    (r"\bretrieval augmented generation\b|\brag\b", "RAG"),
    (r"\bvector databases?\b", "vector-DB"),
    (r"\bdata integration\b", "data-integration"),
    (r"\bml systems?\b|\bmachine learning systems?\b", "ML-systems"),
    (r"\bllm\b.*\bdatabase\b|\bdatabase\b.*\bllm\b", "LLM-DB"),
    (r"\bdata management\b", "LLM-DB"),
    (r"\bdatabase systems?\b", "LLM-DB"),
]

STOPWORDS = {
    "of", "the", "and", "for", "at", "de", "da", "di", "du", "la", "le",
    "der", "die", "das", "von", "zur", "zu", "in", "on", "to", "a", "an",
}

COUNTRY_CODE_TO_COUNTRY = {
    "AR": "Argentina",
    "AU": "Australia",
    "AT": "Austria",
    "BE": "Belgium",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CL": "Chile",
    "CN": "China",
    "CZ": "Czech Republic",
    "DE": "Germany",
    "DK": "Denmark",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "HK": "Hong Kong",
    "HU": "Hungary",
    "IE": "Ireland",
    "IL": "Israel",
    "IN": "India",
    "IT": "Italy",
    "JP": "Japan",
    "KR": "Republic of Korea",
    "MX": "Mexico",
    "MY": "Malaysia",
    "NL": "Netherlands",
    "NO": "Norway",
    "NZ": "New Zealand",
    "PL": "Poland",
    "PT": "Portugal",
    "QA": "Qatar",
    "RU": "Russia",
    "SA": "Saudi Arabia",
    "SE": "Sweden",
    "SG": "Singapore",
    "TH": "Thailand",
    "TR": "Turkey",
    "TW": "Taiwan",
    "UA": "Ukraine",
    "US": "United States",
    "VN": "Vietnam",
    "ZA": "South Africa",
    "AE": "United Arab Emirates",
    "MO": "Macao",
}

COUNTRY_CODE_TO_REGION = {
    "AR": "South America",
    "AU": "Oceania",
    "AT": "Europe",
    "BE": "Europe",
    "BR": "South America",
    "CA": "North America",
    "CH": "Europe",
    "CL": "South America",
    "CN": "Asia",
    "CZ": "Europe",
    "DE": "Europe",
    "DK": "Europe",
    "ES": "Europe",
    "FI": "Europe",
    "FR": "Europe",
    "GB": "Europe",
    "HK": "Asia",
    "HU": "Europe",
    "IE": "Europe",
    "IL": "Asia",
    "IN": "Asia",
    "IT": "Europe",
    "JP": "Asia",
    "KR": "Asia",
    "MX": "North America",
    "MY": "Asia",
    "NL": "Europe",
    "NO": "Europe",
    "NZ": "Oceania",
    "PL": "Europe",
    "PT": "Europe",
    "QA": "Asia",
    "RU": "Europe",
    "SA": "Asia",
    "SE": "Europe",
    "SG": "Asia",
    "TH": "Asia",
    "TR": "Asia",
    "TW": "Asia",
    "UA": "Europe",
    "US": "North America",
    "VN": "Asia",
    "ZA": "Africa",
    "AE": "Asia",
    "MO": "Asia",
}

SPECIAL_ALIASES = {
    "HKU": [
        "University of Hong Kong",
        "The University of Hong Kong",
        "HKU",
    ],
    "HKUST": [
        "Hong Kong University of Science and Technology",
        "HKUST",
    ],
    "USTC": [
        "University of Science and Technology of China",
        "USTC",
    ],
    "Berkeley": [
        "University of California, Berkeley",
        "University of California Berkeley",
        "UC Berkeley",
        "UCB",
    ],
    "UIUC": [
        "University of Illinois Urbana-Champaign",
        "University of Illinois at Urbana-Champaign",
        "UIUC",
    ],
    "EPFL": [
        "Ecole Polytechnique Federale de Lausanne",
        "Ecole Polytechnique Federale Lausanne",
        "EPFL",
    ],
    "ETH": [
        "ETH Zurich",
        "Swiss Federal Institute of Technology Zurich",
    ],
    "TUM": [
        "Technical University of Munich",
        "TU Munich",
        "TUM",
    ],
    "UNSW": [
        "University of New South Wales",
        "UNSW Sydney",
        "UNSW",
    ],
}


def strip_accents(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def normalize_tokens(text: str) -> List[str]:
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return [tok for tok in text.split() if tok and tok not in STOPWORDS]


def signature(text: str) -> Dict[str, Any]:
    tokens = normalize_tokens(text)
    return {
        "normalized": " ".join(tokens),
        "initials": "".join(tok[0] for tok in tokens),
        "tokens": set(tokens),
    }


def normalize_name(text: str) -> str:
    return " ".join(normalize_tokens(text))


def reconstruct_abstract(work: Dict[str, Any]) -> str:
    inverted = work.get("abstract_inverted_index") or {}
    if not inverted:
        return ""
    max_pos = 0
    for positions in inverted.values():
        if positions:
            max_pos = max(max_pos, max(positions))
    tokens = [""] * (max_pos + 1)
    for word, positions in inverted.items():
        for pos in positions:
            if 0 <= pos < len(tokens):
                tokens[pos] = word
    return " ".join(tok for tok in tokens if tok)


def venue_label(work: Dict[str, Any]) -> str:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    label = source.get("display_name") or ""
    if label:
        return label
    host_venue = work.get("host_venue") or {}
    return host_venue.get("display_name") or ""


def work_url(work: Dict[str, Any]) -> str:
    primary_location = work.get("primary_location") or {}
    if primary_location.get("landing_page_url"):
        return primary_location["landing_page_url"]
    doi = work.get("doi") or ""
    if doi:
        return doi if doi.startswith("http") else f"https://doi.org/{doi}"
    return work.get("id") or ""


def dedupe_preserve(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    result: List[str] = []
    for item in items:
        candidate = " ".join((item or "").split()).strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        result.append(candidate)
    return result


def alias_variants(text: str) -> List[str]:
    if not text:
        return []

    aliases: List[str] = [text, strip_accents(text)]
    plain = re.sub(r"\s+", " ", aliases[-1]).strip()
    if plain.lower().startswith("the "):
        aliases.append(plain[4:].strip())

    without_parens = re.sub(r"\s*\([^)]*\)", "", plain).strip()
    if without_parens and without_parens != plain:
        aliases.append(without_parens)

    inside_parens = re.findall(r"\(([^)]*)\)", plain)
    aliases.extend(part.strip() for part in inside_parens if part.strip())

    tokens = normalize_tokens(text)
    if len(tokens) > 1:
        acronym = "".join(tok[0] for tok in tokens if tok)
        if len(acronym) >= 2:
            aliases.append(acronym.upper())

    return dedupe_preserve(aliases)


def supplemental_aliases_for_display_name(display_name: str) -> List[str]:
    if not display_name:
        return []

    normalized = normalize_name(display_name)
    extras: List[str] = []
    for aliases in SPECIAL_ALIASES.values():
        normalized_aliases = [normalize_name(alias) for alias in aliases if alias]
        if any(
            alias_norm
            and (
                alias_norm == normalized
                or alias_norm in normalized
                or normalized in alias_norm
            )
            for alias_norm in normalized_aliases
        ):
            extras.extend(aliases)
    return dedupe_preserve(extras)


def ranking_aliases(display_name: str) -> List[str]:
    return dedupe_preserve(alias_variants(display_name) + supplemental_aliases_for_display_name(display_name))


def country_name_from_code(country_code: str) -> str:
    if not country_code:
        return ""
    return COUNTRY_CODE_TO_COUNTRY.get(country_code.upper(), country_code.upper())


def region_from_country_code(country_code: str) -> str:
    if not country_code:
        return ""
    return COUNTRY_CODE_TO_REGION.get(country_code.upper(), "")


def load_qs_rankings() -> List[Dict[str, Any]]:
    if not QS_RANKINGS_PATH.exists():
        raise FileNotFoundError(f"Missing QS ranking cache: {QS_RANKINGS_PATH}")

    with open(QS_RANKINGS_PATH, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, dict):
        raw_rankings = payload.get("rankings") or payload.get("results") or []
    else:
        raw_rankings = payload

    rankings: List[Dict[str, Any]] = []
    for item in raw_rankings:
        display_name = item.get("display_name") or item.get("name") or ""
        rank = item.get("rank")
        if not display_name or rank is None:
            continue
        try:
            rank_int = int(rank)
        except (TypeError, ValueError):
            continue
        if rank_int > 100:
            continue
        rankings.append({"rank": rank_int, "display_name": display_name})

    rankings.sort(key=lambda item: (item["rank"], normalize_name(item["display_name"])))
    return rankings


def score_qs_institution_candidate(candidate_text: str, display_name: str) -> int:
    cand = signature(candidate_text)
    scores = []
    for alias in ranking_aliases(display_name):
        ali = signature(alias)
        score = 0
        if cand["normalized"] and ali["normalized"] and cand["normalized"] == ali["normalized"]:
            score += 12
        if cand["normalized"] and ali["normalized"] and (
            cand["normalized"] in ali["normalized"] or ali["normalized"] in cand["normalized"]
        ):
            score += 6
        if cand["initials"] and ali["initials"] and cand["initials"] == ali["initials"]:
            score += 8
        overlap = cand["tokens"] & ali["tokens"]
        score += 3 * len(overlap)
        if overlap and any(len(tok) >= 4 for tok in overlap):
            score += 1
        compact_cand = cand["normalized"].replace(" ", "")
        compact_alias = ali["normalized"].replace(" ", "")
        if compact_cand and compact_alias and compact_cand == compact_alias:
            score += 4
        scores.append(score)
    return max(scores) if scores else 0


def match_qs_institution(candidate_text: str, qs_rankings: List[Dict[str, Any]]) -> Optional[Tuple[Dict[str, Any], int]]:
    best: Optional[Tuple[Dict[str, Any], int]] = None
    for entry in qs_rankings:
        score = score_qs_institution_candidate(candidate_text, entry["display_name"])
        if best is None or score > best[1]:
            best = (entry, score)
    if best and best[1] >= 6:
        return best
    return None


def make_generated_institution_key(display_name: str, existing_keys: Iterable[str]) -> str:
    tokens = normalize_tokens(display_name)
    base = ""
    if tokens:
        base = "QS_" + "".join(tok.title() for tok in tokens[:5])
    else:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "", strip_accents(display_name))
        if cleaned:
            base = f"QS_{cleaned[:40]}"
    if not base:
        base = "QS_UnknownInstitution"

    candidate = base
    suffix = 2
    existing = set(existing_keys)
    while candidate in existing:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def score_institution_candidate(candidate_text: str, inst_key: str, inst_meta: Dict[str, Any]) -> int:
    cand = signature(candidate_text)
    scores = []
    aliases = [inst_key, inst_meta.get("display_name", "")] + SPECIAL_ALIASES.get(inst_key, [])
    for alias in aliases:
        if not alias:
            continue
        ali = signature(alias)
        score = 0
        if cand["normalized"] and ali["normalized"] and cand["normalized"] == ali["normalized"]:
            score += 12
        if cand["normalized"] and ali["normalized"] and (
            cand["normalized"] in ali["normalized"] or ali["normalized"] in cand["normalized"]
        ):
            score += 6
        if cand["initials"] and ali["initials"] and cand["initials"] == ali["initials"]:
            score += 8
        overlap = cand["tokens"] & ali["tokens"]
        score += 3 * len(overlap)
        if overlap and any(len(tok) >= 4 for tok in overlap):
            score += 1
        compact_cand = cand["normalized"].replace(" ", "")
        compact_alias = ali["normalized"].replace(" ", "")
        if compact_cand and compact_alias and compact_cand == compact_alias:
            score += 4
        scores.append(score)
    return max(scores) if scores else 0


def match_institution(candidate_text: str, known_institutions: Dict[str, Dict[str, Any]]) -> Optional[Tuple[str, Dict[str, Any], int]]:
    best: Optional[Tuple[str, Dict[str, Any], int]] = None
    for key, meta in known_institutions.items():
        score = score_institution_candidate(candidate_text, key, meta)
        if best is None or score > best[2]:
            best = (key, meta, score)
    if best and best[2] >= 6:
        return best
    return None


def work_tags(text: str) -> List[str]:
    tags: List[str] = []
    for pattern, tag in KEYWORD_PATTERNS:
        if re.search(pattern, text, flags=re.IGNORECASE):
            tags.append(tag)
    # Preserve order but drop duplicates.
    return list(dict.fromkeys(tags))


def work_score(work: Dict[str, Any]) -> Tuple[int, List[str], str]:
    text = " ".join(
        part
        for part in [
            work.get("display_name") or "",
            reconstruct_abstract(work),
        ]
        if part
    )
    tags = work_tags(text)
    venue = venue_label(work).lower()
    score = len(tags)
    if any(marker in venue for marker in VENUE_MARKERS):
        score += 1
    if "arxiv" in venue:
        score += 1
    return score, tags, venue_label(work)


def paper_signature(title: str, venue: str) -> str:
    return f"{normalize_name(title)}|{normalize_name(venue)}"


def build_existing_index(researchers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for entry in researchers:
        name_key = normalize_name(entry.get("name", ""))
        if name_key and name_key not in index:
            index[name_key] = entry
    return index


def choose_author(
    authorships: List[Dict[str, Any]],
    authorship_matches: List[set[str]],
    matched_key: str,
) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for idx, authorship in enumerate(authorships):
        if matched_key not in authorship_matches[idx]:
            continue

        author = authorship.get("author") or {}
        author_name = author.get("display_name") or ""
        if not author_name:
            continue
        candidates.append(
            {
                "author_name": author_name,
                "author_index": idx,
                "is_corresponding": bool(authorship.get("is_corresponding")),
            }
        )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            1 if item["is_corresponding"] else 0,
            item["author_index"],
        ),
        reverse=True,
    )
    return candidates[0]


def append_notable_paper(entry: Dict[str, Any], paper: Dict[str, str], today: str) -> bool:
    notable = entry.setdefault("notable_papers", [])
    signature_key = paper_signature(paper["title"], paper["venue"])
    existing = {paper_signature(p.get("title", ""), p.get("venue", "")) for p in notable}
    if signature_key in existing:
        return False
    notable.append(paper)
    entry["last_updated"] = today
    return True


def build_new_entry(
    *,
    researcher_name: str,
    inst_key: str,
    inst_meta: Dict[str, Any],
    inst_display_name: str,
    inst_qs_rank: int,
    paper: Dict[str, str],
    tags: List[str],
    today: str,
) -> Dict[str, Any]:
    focus = tags[:] if tags else ["database systems"]
    return {
        "id": None,  # Filled by caller.
        "name": researcher_name,
        "type": "faculty",
        "institution": inst_key,
        "institution_display_name": inst_display_name,
        "institution_qs_rank": inst_qs_rank,
        "department": "",
        "country": inst_meta.get("country", ""),
        "region": inst_meta.get("region", ""),
        "position": "",
        "research_focus": focus,
        "tags": tags,
        "homepage": "",
        "email": "",
        "google_scholar": "",
        "notable_papers": [paper],
        "research_group_url": "",
        "currently_taking_students": False,
        "admission_chance": "medium",
        "application_status": "considering",
        "priority": "medium",
        "contact_history": [],
        "notes": (
            f"Auto-discovered from QS #{inst_qs_rank} school {inst_display_name} via {paper['venue']} paper \"{paper['title']}\". "
            "Please verify homepage and student availability manually."
        ),
        "added_date": today,
        "last_updated": today,
    }


def fetch_openalex_works(
    session: requests.Session,
    *,
    query: str,
    start_date: str,
    end_date: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    max_pages: int = MAX_PAGES_PER_QUERY,
) -> Iterable[Dict[str, Any]]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{start_date},to_publication_date:{end_date}",
        "per-page": page_size,
        "page": 1,
    }
    mailto = os.getenv("OPENALEX_MAILTO", "").strip()
    if mailto:
        params["mailto"] = mailto

    for page in range(1, max_pages + 1):
        params["page"] = page
        response = session.get(OPENALEX_WORKS_API, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") or []
        if not results:
            break
        for work in results:
            yield work
        if len(results) < page_size:
            break


def collect_works(session: requests.Session, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for query in SEARCH_TERMS:
        try:
            for work in fetch_openalex_works(session, query=query, start_date=start_date, end_date=end_date):
                work_id = work.get("id") or work.get("openalex_id") or work.get("display_name")
                if not work_id:
                    continue
                if work_id not in seen:
                    seen[work_id] = work
        except requests.RequestException as exc:
            print(f"[warn] OpenAlex query failed for '{query}': {exc}", file=sys.stderr)
    return list(seen.values())


def discover(
    data: Dict[str, Any],
    institutions: Dict[str, Dict[str, Any]],
    qs_rankings: List[Dict[str, Any]],
    works: List[Dict[str, Any]],
    today: str,
) -> Dict[str, Any]:
    known_universities = {
        key: meta
        for key, meta in institutions.items()
        if meta.get("type") == "university"
    }
    existing_index = build_existing_index(data["researchers"])
    additions: List[Dict[str, Any]] = []
    updated_existing = 0
    skipped_due_to_score = 0
    skipped_due_to_match = 0
    paper_updates = 0
    matched_papers = 0
    generated_keys: set[str] = set()

    for work in works:
        score, tags, venue = work_score(work)
        if score < 2:
            skipped_due_to_score += 1
            continue

        authorships = work.get("authorships") or []
        if not authorships:
            skipped_due_to_match += 1
            continue

        work_title = work.get("display_name") or ""
        if not work_title:
            skipped_due_to_match += 1
            continue

        paper = {
            "title": work_title,
            "venue": venue or "OpenAlex",
            "url": work_url(work),
        }

        authorship_matches: List[set[str]] = [set() for _ in authorships]
        matched_insts: Dict[str, Dict[str, Any]] = {}

        for idx, authorship in enumerate(authorships):
            author_institutions = list(authorship.get("institutions") or [])
            if not author_institutions:
                author_institutions = [{}]

            candidate_texts: List[Tuple[str, Dict[str, Any]]] = []
            for inst in authorship.get("institutions") or []:
                display = inst.get("display_name") or ""
                if display:
                    candidate_texts.append((display, inst))
            for raw in authorship.get("raw_affiliation_strings") or []:
                if raw:
                    candidate_texts.append((raw, author_institutions[0]))

            for candidate_text, inst_obj in candidate_texts:
                qs_match = match_qs_institution(candidate_text, qs_rankings)
                if not qs_match:
                    continue

                qs_entry, _ = qs_match
                known_match = match_institution(candidate_text, known_universities)
                inst_rank = int(qs_entry["rank"])

                if known_match:
                    inst_key, inst_meta, _ = known_match
                    inst_display_name = inst_meta.get("display_name", inst_key)
                else:
                    inst_display_name = qs_entry["display_name"]
                    inst_key = make_generated_institution_key(
                        inst_display_name,
                        list(institutions.keys()) + list(generated_keys),
                    )
                    generated_keys.add(inst_key)
                    country_code = (inst_obj or {}).get("country_code") or ""
                    inst_meta = {
                        "display_name": inst_display_name,
                        "city": "",
                        "country": country_name_from_code(country_code),
                        "region": region_from_country_code(country_code),
                        "lat": None,
                        "lon": None,
                        "qs_rank": inst_rank,
                        "type": "university",
                    }

                authorship_matches[idx].add(inst_key)
                matched_insts.setdefault(
                    inst_key,
                    {
                        "meta": inst_meta,
                        "display_name": inst_display_name,
                        "qs_rank": inst_rank,
                    },
                )

        if not matched_insts:
            skipped_due_to_match += 1
            continue

        matched_papers += 1

        # Try to update existing entries first. If a researcher is already in the
        # dataset, we only append missing papers.
        for inst_key in sorted(matched_insts):
            chosen = choose_author(authorships, authorship_matches, inst_key)
            if not chosen:
                continue

            chosen_name = chosen["author_name"]
            existing = existing_index.get(normalize_name(chosen_name))
            if existing:
                if append_notable_paper(existing, paper, today):
                    paper_updates += 1
                    updated_existing += 1
                continue

            inst_record = matched_insts[inst_key]
            candidate = build_new_entry(
                researcher_name=chosen_name,
                inst_key=inst_key,
                inst_meta=inst_record["meta"],
                inst_display_name=inst_record["display_name"],
                inst_qs_rank=inst_record["qs_rank"],
                paper=paper,
                tags=tags,
                today=today,
            )
            candidate["id"] = next_id(data["researchers"] + additions)
            additions.append(candidate)
            existing_index[normalize_name(chosen_name)] = candidate
            paper_updates += 1

    if additions:
        data["researchers"].extend(additions)
    if paper_updates:
        # Keep the overall meta timestamp fresh even if no file write occurs.
        data.setdefault("meta", {})["last_updated"] = today

    return {
        "added": additions,
        "updated_existing": updated_existing,
        "skipped_due_to_score": skipped_due_to_score,
        "skipped_due_to_match": skipped_due_to_match,
        "paper_updates": paper_updates,
        "matched_papers": matched_papers,
        "total_works": len(works),
    }


def summarize(report: Dict[str, Any]) -> str:
    lines = [
        f"Scanned works: {report['total_works']}",
        f"New researchers added: {len(report['added'])}",
        f"Existing researchers updated: {report['updated_existing']}",
        f"Paper records appended: {report['paper_updates']}",
        f"Matched papers: {report['matched_papers']}",
        f"Skipped by relevance score: {report['skipped_due_to_score']}",
        f"Skipped by institution matching: {report['skipped_due_to_match']}",
    ]
    if report["added"]:
        lines.append("Added researchers:")
        for entry in report["added"]:
            inst_label = entry.get("institution_display_name") or entry["institution"]
            lines.append(f"  - {entry['name']} ({inst_label})")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover AI4DB researchers from OpenAlex")
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="How many days back to scan (default: 21)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates back to data/researchers.json",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force read-only mode even if --apply is present",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data = load_researchers()
    institutions = load_institutions()
    qs_rankings = load_qs_rankings()

    today = date.today().isoformat()
    start_date = (date.fromisoformat(today) - timedelta(days=args.lookback_days)).isoformat()

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "ai4db-teams-discovery/1.0 (+https://github.com/lyntele/ai4db-teams)",
        }
    )
    works = collect_works(session, start_date=start_date, end_date=today)
    report = discover(data, institutions, qs_rankings, works, today)

    print(summarize(report))

    if args.apply and not args.dry_run and report["paper_updates"] > 0:
        save_researchers(data)
        print(f"Saved updates to {ROOT_DIR / 'data' / 'researchers.json'}")
    else:
        print("Dry run only. No files were written.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
