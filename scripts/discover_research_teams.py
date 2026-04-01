#!/usr/bin/env python3
"""Discover new AI4DB researchers from recent OpenAlex works.

The script scans recent works for AI4DB-related signals, keeps only database
top-conference / arXiv papers, matches affiliations against a QS-top-100
cache, and then:

1. appends new researchers when the institution matches a QS<100 university,
   even if that school is not already present in ``data/institutions.json``;
2. updates existing researchers by adding missing notable papers.
3. refreshes industrial team entries by folding in authors from related
   papers and reusing existing personal homepages when available.
4. optionally writes a watchlist report so the daily workflow leaves behind a
   human-readable DB+LLM literature digest in the repository.

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
from urllib.parse import urlparse

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
DEFAULT_MEMBER_LOOKBACK_DAYS = 180
QS_RANKINGS_PATH = ROOT_DIR / "data" / "qs_rankings.json"
WATCHLISTS_PATH = ROOT_DIR / "data" / "literature_watchlists.json"
TEAM_NAME_HINTS = ("team", "group", "lab")
MIN_INSTITUTION_MATCH_SCORE = 16
DEFAULT_REPORT_LIMIT = 20
DEFAULT_WATCHLIST_ID = "db_llm"

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

DEFAULT_WATCHLISTS = {
    "default_watchlist": DEFAULT_WATCHLIST_ID,
    "watchlists": [
        {
            "id": DEFAULT_WATCHLIST_ID,
            "name": "DB + LLM",
            "description": "Track papers at the intersection of databases and LLMs, especially NL2SQL, data agents, and SQL reasoning.",
            "search_terms": [
                "text-to-sql",
                "nl2sql",
                "natural language to sql",
                "sql generation language model",
                "llm sql",
                "sql agent",
                "database llm",
                "llm database",
                "database agent",
                "data agent sql",
                "schema linking sql",
                "rag sql",
            ],
            "allowed_tags": [
                "text-to-SQL",
                "NL2SQL",
                "schema-linking",
                "table-QA",
                "data-agents",
                "RAG",
                "LLM-DB",
                "query-optimization",
                "data-integration",
            ],
            "focus_patterns": [
                r"\\btext[- ]?to[- ]?sql\\b",
                r"\\bnl2sql\\b",
                r"\\bnatural language (interface|query|question|rewriter|translation).{0,40}\\bsql\\b",
                r"\\b(llm|large language model|language model|gpt|agentic|data agent|rag)\\b.{0,60}\\b(sql|database|query|schema|table)\\b",
                r"\\b(sql|database|query|schema|table)\\b.{0,60}\\b(llm|large language model|language model|gpt|agentic|data agent|rag)\\b",
            ],
            "venue_markers": VENUE_MARKERS,
            "min_score": 2,
        }
    ],
}

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
    "MSRA": [
        "Microsoft Research Asia",
        "MSRA",
        "Microsoft Research Asia Lab",
    ],
    "MSR": [
        "Microsoft Research",
        "MSR",
        "Microsoft Research Redmond",
    ],
    "GoogleR": [
        "Google Research",
        "Google",
    ],
    "GoogleCloud": [
        "Google Cloud",
        "Google Cloud, Sunnyvale",
        "Google Cloud Sunnyvale",
    ],
    "AliDAMO": [
        "Alibaba DAMO Academy",
        "DAMO Academy",
        "Alibaba",
    ],
    "Salesforce": [
        "Salesforce Research",
        "Salesforce",
    ],
    "MetaAI": [
        "Meta AI Research",
        "Meta AI",
        "FAIR",
        "Meta",
    ],
    "HuaweiNoah": [
        "Huawei Noah's Ark Lab",
        "Huawei Noah",
        "Noah's Ark Lab",
        "Huawei",
    ],
    "ByteDance": [
        "ByteDance AI Lab",
        "ByteDance Seed",
        "ByteDance",
    ],
    "BaiduR": [
        "Baidu Research",
        "Baidu",
    ],
    "TencentAI": [
        "Tencent AI Lab",
        "Tencent",
        "Tencent (China)",
    ],
    "AntGroup": [
        "Ant Group",
        "Ant Group Technology",
        "Ant",
    ],
    "4Paradigm": [
        "4Paradigm",
        "Fourth Paradigm",
    ],
    "AmazonSci": [
        "Amazon Science",
        "Amazon",
    ],
    "Databricks": [
        "Databricks Research",
        "Databricks",
    ],
    "IBM": [
        "IBM Research",
        "IBM",
    ],
    "Oracle": [
        "Oracle Corporation",
        "Oracle",
    ],
    "Snowflake": [
        "Snowflake Research",
        "Snowflake",
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


def root_domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path).lower().strip()
    if host.startswith("www."):
        host = host[4:]
    parts = [part for part in host.split(".") if part]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"ac", "co", "com", "edu", "gov", "net", "org"}:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host


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


def normalize_string_list(items: Iterable[str]) -> List[str]:
    return dedupe_preserve(item for item in items if item)


def default_watchlists_payload() -> Dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_WATCHLISTS))


def load_watchlists() -> Dict[str, Any]:
    payload: Dict[str, Any]
    if WATCHLISTS_PATH.exists():
        with open(WATCHLISTS_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = default_watchlists_payload()

    raw_watchlists = payload.get("watchlists") or []
    watchlists: Dict[str, Dict[str, Any]] = {}

    for raw in raw_watchlists:
        watchlist_id = (raw.get("id") or raw.get("name") or "").strip()
        if not watchlist_id:
            continue
        watchlists[watchlist_id] = {
            "id": watchlist_id,
            "name": (raw.get("name") or watchlist_id).strip(),
            "description": (raw.get("description") or "").strip(),
            "search_terms": normalize_string_list(raw.get("search_terms") or SEARCH_TERMS),
            "allowed_tags": normalize_string_list(raw.get("allowed_tags") or []),
            "focus_patterns": normalize_string_list(raw.get("focus_patterns") or []),
            "venue_markers": [marker.lower() for marker in normalize_string_list(raw.get("venue_markers") or VENUE_MARKERS)],
            "min_score": int(raw.get("min_score") or 2),
        }

    if not watchlists:
        fallback = default_watchlists_payload()
        return {
            "default_watchlist": fallback["default_watchlist"],
            "watchlists": {
                item["id"]: {
                    "id": item["id"],
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "search_terms": normalize_string_list(item.get("search_terms") or SEARCH_TERMS),
                    "allowed_tags": normalize_string_list(item.get("allowed_tags") or []),
                    "focus_patterns": normalize_string_list(item.get("focus_patterns") or []),
                    "venue_markers": [marker.lower() for marker in normalize_string_list(item.get("venue_markers") or VENUE_MARKERS)],
                    "min_score": int(item.get("min_score") or 2),
                }
                for item in fallback["watchlists"]
            },
        }

    default_watchlist = (payload.get("default_watchlist") or "").strip()
    if default_watchlist not in watchlists:
        default_watchlist = next(iter(watchlists))

    return {
        "default_watchlist": default_watchlist,
        "watchlists": watchlists,
    }


def resolve_watchlist(watchlists_payload: Dict[str, Any], requested_id: str) -> Dict[str, Any]:
    watchlists = watchlists_payload.get("watchlists") or {}
    if requested_id in watchlists:
        return watchlists[requested_id]
    available = ", ".join(sorted(watchlists))
    raise KeyError(f"Unknown watchlist '{requested_id}'. Available watchlists: {available}")


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
    # Weak fuzzy matches create bad imports like York -> NYU or UCSB -> Berkeley.
    if best and best[1] >= MIN_INSTITUTION_MATCH_SCORE:
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
    if best and best[2] >= MIN_INSTITUTION_MATCH_SCORE:
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
    text = work_text(work)
    tags = work_tags(text)
    venue = venue_label(work).lower()
    score = len(tags)
    if any(marker in venue for marker in VENUE_MARKERS):
        score += 1
    if "arxiv" in venue:
        score += 1
    return score, tags, venue_label(work)


def work_text(work: Dict[str, Any]) -> str:
    return " ".join(
        part
        for part in [
            work.get("display_name") or "",
            reconstruct_abstract(work),
        ]
        if part
    )


def work_matches_watchlist(work: Dict[str, Any], watchlist: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    score, tags, venue = work_score(work)
    venue_lower = venue.lower()
    min_score = int(watchlist.get("min_score") or 2)
    if score < min_score:
        return False, {"reason": "score", "score": score, "tags": tags, "venue": venue}

    venue_markers = watchlist.get("venue_markers") or [marker.lower() for marker in VENUE_MARKERS]
    if not any(marker in venue_lower for marker in venue_markers) and "arxiv" not in venue_lower:
        return False, {"reason": "venue", "score": score, "tags": tags, "venue": venue}

    text = work_text(work)
    allowed_tags = set(watchlist.get("allowed_tags") or [])
    focus_patterns = watchlist.get("focus_patterns") or []
    focus_match = bool(allowed_tags & set(tags))
    if not focus_match and focus_patterns:
        focus_match = any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in focus_patterns)
    if not focus_match:
        return False, {"reason": "focus", "score": score, "tags": tags, "venue": venue}

    return True, {"reason": "", "score": score, "tags": tags, "venue": venue}


def filter_works_for_watchlist(
    works: List[Dict[str, Any]],
    watchlist: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    filtered: List[Dict[str, Any]] = []
    stats = {
        "fetched_works": len(works),
        "matched_watchlist_works": 0,
        "skipped_due_to_score": 0,
        "skipped_due_to_venue": 0,
        "skipped_due_to_focus": 0,
    }
    for work in works:
        matches, meta = work_matches_watchlist(work, watchlist)
        if matches:
            filtered.append(work)
            stats["matched_watchlist_works"] += 1
            continue
        reason = meta["reason"]
        if reason == "score":
            stats["skipped_due_to_score"] += 1
        elif reason == "venue":
            stats["skipped_due_to_venue"] += 1
        elif reason == "focus":
            stats["skipped_due_to_focus"] += 1
    return filtered, stats


def publication_date_label(work: Dict[str, Any]) -> str:
    return (work.get("publication_date") or work.get("from_publication_date") or "").strip()


def authorship_affiliation_label(authorship: Dict[str, Any]) -> str:
    institutions = authorship.get("institutions") or []
    labels = dedupe_preserve(inst.get("display_name") or "" for inst in institutions)
    if labels:
        return ", ".join(labels[:2])
    raw = dedupe_preserve(authorship.get("raw_affiliation_strings") or [])
    if raw:
        return raw[0]
    return ""


def report_author_labels(work: Dict[str, Any]) -> List[str]:
    labels: List[str] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        affiliation = authorship_affiliation_label(authorship)
        if affiliation:
            labels.append(f"{name} ({affiliation})")
        else:
            labels.append(name)
    return labels


def report_author_records(work: Dict[str, Any]) -> List[Dict[str, str]]:
    records: List[Dict[str, str]] = []
    for authorship in work.get("authorships") or []:
        author = authorship.get("author") or {}
        name = (author.get("display_name") or "").strip()
        if not name:
            continue
        records.append(
            {
                "name": name,
                "affiliation": authorship_affiliation_label(authorship),
                "is_corresponding": bool(authorship.get("is_corresponding")),
            }
        )
    return records


def build_report_payload(
    *,
    watchlist: Dict[str, Any],
    raw_stats: Dict[str, int],
    filtered_works: List[Dict[str, Any]],
    report: Dict[str, Any],
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    sorted_works = sorted(
        filtered_works,
        key=lambda work: (
            publication_date_label(work),
            (work.get("display_name") or "").casefold(),
        ),
        reverse=True,
    )
    return {
        "watchlist_id": watchlist["id"],
        "watchlist_name": watchlist["name"],
        "description": watchlist.get("description", ""),
        "search_terms": watchlist.get("search_terms", []),
        "run_date": end_date,
        "scan_window": {"start_date": start_date, "end_date": end_date},
        "summary": {
            "openalex_works_fetched": raw_stats["fetched_works"],
            "watchlist_matches": raw_stats["matched_watchlist_works"],
            "new_researchers_added": len(report["added"]),
            "existing_researchers_updated": report["updated_existing"],
            "industrial_members_added": report["team_member_additions"],
            "industrial_members_updated": report["team_member_updates"],
            "papers_mapped_to_site_entries": report["matched_papers"],
            "skipped_due_to_score": raw_stats["skipped_due_to_score"],
            "skipped_due_to_venue": raw_stats["skipped_due_to_venue"],
            "skipped_due_to_focus": raw_stats["skipped_due_to_focus"],
            "skipped_due_to_institution": report["skipped_due_to_match"],
            "skipped_due_to_role": report["skipped_due_to_role"],
        },
        "new_researchers": [
            {
                "name": entry["name"],
                "institution": entry.get("institution_display_name") or entry.get("institution", ""),
                "tags": entry.get("tags", []),
            }
            for entry in report["added"]
        ],
        "papers": [
            {
                "title": work.get("display_name") or "",
                "publication_date": publication_date_label(work),
                "venue": venue_label(work),
                "tags": work_score(work)[1],
                "relevance_score": work_score(work)[0],
                "url": work_url(work),
                "authors": report_author_records(work),
            }
            for work in sorted_works
        ],
    }


def build_report_markdown(
    *,
    watchlist: Dict[str, Any],
    raw_stats: Dict[str, int],
    filtered_works: List[Dict[str, Any]],
    report: Dict[str, Any],
    start_date: str,
    end_date: str,
    report_limit: int,
) -> str:
    lines = [
        f"# {watchlist['name']} Daily Literature Watch",
        "",
        f"- Run date: {end_date}",
        f"- Scan window: {start_date} to {end_date}",
        f"- Watchlist id: `{watchlist['id']}`",
    ]
    if watchlist.get("description"):
        lines.append(f"- Scope: {watchlist['description']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- OpenAlex works fetched: {raw_stats['fetched_works']}")
    lines.append(f"- Works matching this watchlist: {raw_stats['matched_watchlist_works']}")
    lines.append(f"- New researchers added to site: {len(report['added'])}")
    lines.append(f"- Existing researchers updated: {report['updated_existing']}")
    lines.append(f"- Industrial team members added: {report['team_member_additions']}")
    lines.append(f"- Industrial team members updated: {report['team_member_updates']}")
    lines.append(f"- Papers that mapped to site entries: {report['matched_papers']}")
    lines.append(f"- Skipped by relevance score: {raw_stats['skipped_due_to_score']}")
    lines.append(f"- Skipped by venue: {raw_stats['skipped_due_to_venue']}")
    lines.append(f"- Skipped by DB+LLM focus filter: {raw_stats['skipped_due_to_focus']}")
    lines.append(f"- Skipped by institution matching: {report['skipped_due_to_match']}")
    lines.append(f"- Skipped by author-role guardrail: {report['skipped_due_to_role']}")

    if report["added"]:
        lines.extend(["", "## Newly Added Researchers", ""])
        for entry in report["added"]:
            inst_label = entry.get("institution_display_name") or entry.get("institution") or ""
            lines.append(f"- {entry['name']} ({inst_label})")

    if filtered_works:
        lines.extend(["", "## Matched Papers", ""])
        sorted_works = sorted(
            filtered_works,
            key=lambda work: (
                publication_date_label(work),
                (work.get("display_name") or "").casefold(),
            ),
            reverse=True,
        )
        for idx, work in enumerate(sorted_works[:report_limit], start=1):
            score, tags, venue = work_score(work)
            lines.append(f"### {idx}. {work.get('display_name') or 'Untitled work'}")
            lines.append(f"- Publication date: {publication_date_label(work) or 'unknown'}")
            lines.append(f"- Venue: {venue or 'OpenAlex'}")
            lines.append(f"- Tags: {', '.join(tags) if tags else 'none'}")
            lines.append(f"- Relevance score: {score}")
            lines.append(f"- URL: {work_url(work) or 'n/a'}")
            authors = report_author_labels(work)
            if authors:
                lines.append(f"- Authors: {'; '.join(authors[:12])}")
            lines.append("")
        remaining = len(filtered_works) - min(len(filtered_works), report_limit)
        if remaining > 0:
            lines.append(f"_Omitted {remaining} additional matched papers from the markdown report to keep it readable._")
    else:
        lines.extend(["", "## Matched Papers", "", "_No DB+LLM papers matched this run._"])

    return "\n".join(lines).rstrip() + "\n"


def write_watchlist_report(
    *,
    output_dir: Path,
    watchlist: Dict[str, Any],
    raw_stats: Dict[str, int],
    filtered_works: List[Dict[str, Any]],
    report: Dict[str, Any],
    start_date: str,
    end_date: str,
    report_limit: int,
    archive: bool,
    skip_empty: bool,
) -> List[Path]:
    if skip_empty and not filtered_works and not report["added"] and not report["paper_updates"]:
        return []

    base_dir = output_dir / watchlist["id"]
    base_dir.mkdir(parents=True, exist_ok=True)
    content = build_report_markdown(
        watchlist=watchlist,
        raw_stats=raw_stats,
        filtered_works=filtered_works,
        report=report,
        start_date=start_date,
        end_date=end_date,
        report_limit=report_limit,
    )

    written: List[Path] = []
    latest_path = base_dir / "latest.md"
    latest_path.write_text(content, encoding="utf-8")
    written.append(latest_path)

    payload = build_report_payload(
        watchlist=watchlist,
        raw_stats=raw_stats,
        filtered_works=filtered_works,
        report=report,
        start_date=start_date,
        end_date=end_date,
    )
    latest_json_path = base_dir / "latest.json"
    latest_json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(latest_json_path)

    if archive:
        archive_path = base_dir / f"{end_date}.md"
        archive_path.write_text(content, encoding="utf-8")
        written.append(archive_path)
        archive_json_path = base_dir / f"{end_date}.json"
        archive_json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(archive_json_path)

    return written


def paper_signature(title: str, venue: str) -> str:
    return f"{normalize_name(title)}|{normalize_name(venue)}"


def build_existing_index(researchers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for entry in researchers:
        name_key = normalize_name(entry.get("name", ""))
        if name_key and name_key not in index:
            index[name_key] = entry
    return index


def matched_author_candidates(
    authorships: List[Dict[str, Any]],
    authorship_matches: List[set[str]],
    matched_key: str,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    total_authors = len(authorships)
    for idx, authorship in enumerate(authorships):
        if matched_key not in authorship_matches[idx]:
            continue

        author = authorship.get("author") or {}
        author_name = author.get("display_name") or ""
        if not author_name:
            continue

        is_corresponding = bool(authorship.get("is_corresponding"))
        is_single_author = total_authors == 1
        is_last_author = total_authors > 1 and idx == total_authors - 1
        author_position = (authorship.get("author_position") or "").lower()
        has_senior_signal = is_corresponding or is_last_author or is_single_author

        candidates.append(
            {
                "author_name": author_name,
                "author_index": idx,
                "author_position": author_position,
                "is_corresponding": is_corresponding,
                "is_last_author": is_last_author,
                "is_single_author": is_single_author,
                "has_senior_signal": has_senior_signal,
            }
        )

    candidates.sort(
        key=lambda item: (
            1 if item["has_senior_signal"] else 0,
            1 if item["is_corresponding"] else 0,
            1 if item["is_last_author"] else 0,
            1 if item["is_single_author"] else 0,
            item["author_index"],
        ),
        reverse=True,
    )
    return candidates


def is_industry_team_entry(entry: Dict[str, Any]) -> bool:
    if entry.get("type") != "industry":
        return False
    name = (entry.get("name") or "").lower()
    position = (entry.get("position") or "").lower()
    return bool(entry.get("members")) or any(hint in name for hint in TEAM_NAME_HINTS) or any(
        hint in position for hint in TEAM_NAME_HINTS
    )


def build_member_profile_index(researchers: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    index: Dict[str, Dict[str, str]] = {}

    def maybe_set(name: str, profile: Dict[str, str]) -> None:
        name_key = normalize_name(name)
        if not name_key:
            return
        current = index.get(name_key)
        if current is None:
            index[name_key] = profile
            return
        if not current.get("homepage") and profile.get("homepage"):
            index[name_key] = profile
            return
        if not current.get("position") and profile.get("position"):
            index[name_key] = profile

    for entry in researchers:
        maybe_set(
            entry.get("name", ""),
            {
                "homepage": entry.get("homepage", "") or "",
                "position": entry.get("position", "") or "",
            },
        )
        members = entry.get("members") if isinstance(entry.get("members"), list) else []
        for member in members:
            maybe_set(
                member.get("name", ""),
                {
                    "homepage": member.get("homepage", "") or "",
                    "position": member.get("position", "") or "",
                },
            )

    return index


def industry_member_seed_keys(
    entry: Dict[str, Any],
    institutions: Dict[str, Dict[str, Any]],
) -> List[str]:
    keys: List[str] = []
    inst_key = entry.get("institution", "") or ""
    if inst_key:
        keys.append(f"inst:{inst_key}")

    inst_meta = institutions.get(inst_key, {})
    for url in (
        entry.get("homepage", "") or "",
        entry.get("research_group_url", "") or "",
        inst_meta.get("homepage", "") or "",
        inst_meta.get("url", "") or "",
    ):
        domain = root_domain(url)
        if domain:
            keys.append(f"domain:{domain}")

    return dedupe_preserve(keys)


def existing_member_note(entry: Dict[str, Any]) -> str:
    note = " ".join((entry.get("notes", "") or "").split()).strip()
    if note:
        return f"来自仓库已有个人条目：{note}"
    return "来自仓库已有工业界个人条目。"


def build_existing_industry_member_seeds(
    researchers: List[Dict[str, Any]],
    institutions: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Dict[str, str]]]:
    seed_index: Dict[str, Dict[str, Dict[str, str]]] = {}

    for entry in researchers:
        if entry.get("type") != "industry" or is_industry_team_entry(entry):
            continue

        member_key = normalize_name(entry.get("name", ""))
        if not member_key:
            continue

        profile = {
            "name": entry.get("name", "") or "",
            "position": entry.get("position", "") or "",
            "homepage": entry.get("homepage", "") or "",
            "notes": existing_member_note(entry),
        }
        for seed_key in industry_member_seed_keys(entry, institutions):
            bucket = seed_index.setdefault(seed_key, {})
            current = bucket.get(member_key)
            if current is None:
                bucket[member_key] = profile.copy()
                continue
            if not current.get("homepage") and profile.get("homepage"):
                current["homepage"] = profile["homepage"]
            if not current.get("position") and profile.get("position"):
                current["position"] = profile["position"]
            if not current.get("notes") and profile.get("notes"):
                current["notes"] = profile["notes"]

    return seed_index


def member_evidence_note(team_name: str, candidate: Dict[str, Any]) -> str:
    papers = candidate.get("papers") or []
    samples: List[str] = []
    seen: set[str] = set()
    for paper in papers:
        sig = paper_signature(paper.get("title", ""), paper.get("venue", ""))
        if sig in seen:
            continue
        seen.add(sig)
        samples.append(f'"{paper.get("title", "")}" ({paper.get("venue", "")})')
        if len(samples) >= 2:
            break

    if samples:
        return f"由 {candidate.get('match_count', 0)} 篇相关论文作者回填，示例论文：{'；'.join(samples)}。"
    return f"由相关论文作者回填，来源于 {team_name} 的近期论文。"


def refresh_industry_team_members(
    data: Dict[str, Any],
    institutions: Dict[str, Dict[str, Any]],
    works: List[Dict[str, Any]],
    today: str,
) -> Dict[str, Any]:
    industry_institutions = {
        key: meta for key, meta in institutions.items() if meta.get("type") == "industry"
    }
    team_entries = [entry for entry in data.get("researchers", []) if is_industry_team_entry(entry)]
    if not team_entries:
        return {
            "team_member_additions": 0,
            "team_member_updates": 0,
            "team_entries_touched": 0,
    }

    profile_index = build_member_profile_index(data.get("researchers", []))
    existing_member_seeds = build_existing_industry_member_seeds(
        data.get("researchers", []),
        institutions,
    )
    team_by_inst = {
        entry.get("institution"): entry
        for entry in team_entries
        if entry.get("institution")
    }
    team_tags = {
        entry["id"]: set(entry.get("tags", [])) if isinstance(entry.get("tags"), list) else set()
        for entry in team_entries
    }
    evidence_by_team: Dict[str, Dict[str, Dict[str, Any]]] = {entry["id"]: {} for entry in team_entries}
    seen_pairs: set[Tuple[str, str, str]] = set()

    for work in works:
        score, tags, venue = work_score(work)
        if score < 2:
            continue
        venue_lower = venue.lower()
        if not any(marker in venue_lower for marker in VENUE_MARKERS) and "arxiv" not in venue_lower:
            continue
        tag_set = set(tags)
        if not tag_set:
            continue

        paper = {
            "title": work.get("display_name") or "",
            "venue": venue or "OpenAlex",
            "url": work_url(work),
        }
        paper_sig = paper_signature(paper["title"], paper["venue"])

        authorships = work.get("authorships") or []
        if not authorships:
            continue

        for authorship in authorships:
            author = authorship.get("author") or {}
            author_name = author.get("display_name") or ""
            if not author_name:
                continue
            author_norm = normalize_name(author_name)
            if not author_norm:
                continue

            author_position = (authorship.get("author_position") or "").lower()
            is_corresponding = bool(authorship.get("is_corresponding"))
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

            matched_team_ids: set[str] = set()
            for candidate_text, _inst_obj in candidate_texts:
                match = match_institution(candidate_text, industry_institutions)
                if not match:
                    continue
                team_key, _team_meta, _score = match
                team_entry = team_by_inst.get(team_key)
                if not team_entry:
                    continue
                team_tag_set = team_tags.get(team_entry["id"], set())
                if team_tag_set and not (team_tag_set & tag_set):
                    continue
                matched_team_ids.add(team_entry["id"])

            if not matched_team_ids:
                continue

            for team_id in matched_team_ids:
                pair_key = (team_id, author_norm, paper_sig)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                bucket = evidence_by_team[team_id].setdefault(
                    author_norm,
                    {
                        "name": author_name,
                        "match_count": 0,
                        "first_author_count": 0,
                        "is_corresponding_count": 0,
                        "papers": [],
                    },
                )
                bucket["match_count"] += 1
                bucket["first_author_count"] += int(author_position == "first")
                bucket["is_corresponding_count"] += int(is_corresponding)
                bucket["papers"].append(paper)

    team_member_additions = 0
    team_member_updates = 0
    team_entries_touched = 0

    for entry in team_entries:
        members = entry.get("members") if isinstance(entry.get("members"), list) else []
        merged_members: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        changed = False

        for member in members:
            member_key = normalize_name(member.get("name", ""))
            if not member_key or member_key in merged_members:
                continue
            merged_members[member_key] = {
                "name": member.get("name", "") or "",
                "position": member.get("position", "") or "",
                "homepage": member.get("homepage", "") or "",
                "notes": member.get("notes", "") or "",
            }
            order.append(member_key)

        seeded_members: Dict[str, Dict[str, str]] = {}
        for seed_key in industry_member_seed_keys(entry, institutions):
            for member_key, profile in existing_member_seeds.get(seed_key, {}).items():
                if member_key not in seeded_members:
                    seeded_members[member_key] = profile.copy()
                    continue
                current = seeded_members[member_key]
                if not current.get("homepage") and profile.get("homepage"):
                    current["homepage"] = profile["homepage"]
                if not current.get("position") and profile.get("position"):
                    current["position"] = profile["position"]
                if not current.get("notes") and profile.get("notes"):
                    current["notes"] = profile["notes"]

        for member_key, candidate in sorted(
            seeded_members.items(),
            key=lambda item: item[1].get("name", "").casefold(),
        ):
            if not member_key:
                continue

            if member_key in merged_members:
                member = merged_members[member_key]
                member_changed = False
                if not member.get("homepage") and candidate.get("homepage"):
                    member["homepage"] = candidate["homepage"]
                    member_changed = True
                if not member.get("position") and candidate.get("position"):
                    member["position"] = candidate["position"]
                    member_changed = True
                if not member.get("notes") and candidate.get("notes"):
                    member["notes"] = candidate["notes"]
                    member_changed = True
                if member_changed:
                    merged_members[member_key] = member
                    team_member_updates += 1
                    changed = True
                continue

            merged_members[member_key] = {
                "name": candidate.get("name", "") or "",
                "position": candidate.get("position", "") or "Researcher",
                "homepage": candidate.get("homepage", "") or "",
                "notes": candidate.get("notes", "") or "",
            }
            order.append(member_key)
            team_member_additions += 1
            changed = True

        candidates = list(evidence_by_team.get(entry["id"], {}).values())
        candidates.sort(
            key=lambda item: (
                -int(item.get("match_count", 0)),
                -int(item.get("is_corresponding_count", 0)),
                -int(item.get("first_author_count", 0)),
                item.get("name", "").casefold(),
            )
        )
        for candidate in candidates:
            member_key = normalize_name(candidate.get("name", ""))
            if not member_key:
                continue

            profile = profile_index.get(member_key, {})
            homepage = profile.get("homepage", "") or ""
            position = profile.get("position", "") or ""
            if not position:
                position = "Researcher"

            if member_key in merged_members:
                member = merged_members[member_key]
                member_changed = False
                if not member.get("homepage") and homepage:
                    member["homepage"] = homepage
                    member_changed = True
                if not member.get("position") and position:
                    member["position"] = position
                    member_changed = True
                if not member.get("notes"):
                    member["notes"] = member_evidence_note(entry["name"], candidate)
                    member_changed = True
                if member_changed:
                    merged_members[member_key] = member
                    team_member_updates += 1
                    changed = True
            else:
                merged_members[member_key] = {
                    "name": candidate.get("name", "") or "",
                    "position": position,
                    "homepage": homepage,
                    "notes": member_evidence_note(entry["name"], candidate),
                }
                order.append(member_key)
                team_member_additions += 1
                changed = True

        if changed:
            entry["members"] = [merged_members[key] for key in order if key in merged_members]
            entry["last_updated"] = today
            team_entries_touched += 1

    return {
        "team_member_additions": team_member_additions,
        "team_member_updates": team_member_updates,
        "team_entries_touched": team_entries_touched,
    }


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


def collect_works(
    session: requests.Session,
    start_date: str,
    end_date: str,
    search_terms: List[str],
) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for query in search_terms:
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
    skipped_due_to_venue = 0
    skipped_due_to_match = 0
    skipped_due_to_role = 0
    paper_updates = 0
    matched_papers = 0
    generated_keys: set[str] = set()

    for work in works:
        score, tags, venue = work_score(work)
        if score < 2:
            skipped_due_to_score += 1
            continue
        venue_lower = venue.lower()
        if not any(marker in venue_lower for marker in VENUE_MARKERS) and "arxiv" not in venue_lower:
            skipped_due_to_venue += 1
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
            candidates = matched_author_candidates(authorships, authorship_matches, inst_key)
            if not candidates:
                continue

            matched_existing = False
            for candidate in candidates:
                existing = existing_index.get(normalize_name(candidate["author_name"]))
                if not existing:
                    continue
                matched_existing = True
                if append_notable_paper(existing, paper, today):
                    paper_updates += 1
                    updated_existing += 1
            if matched_existing:
                continue

            chosen = next((candidate for candidate in candidates if candidate["has_senior_signal"]), None)
            if not chosen:
                skipped_due_to_role += 1
                continue

            inst_record = matched_insts[inst_key]
            candidate = build_new_entry(
                researcher_name=chosen["author_name"],
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
            existing_index[normalize_name(chosen["author_name"])] = candidate
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
        "skipped_due_to_venue": skipped_due_to_venue,
        "skipped_due_to_role": skipped_due_to_role,
    }


def summarize(report: Dict[str, Any]) -> str:
    lines = [
        f"Watchlist: {report['watchlist_name']} ({report['watchlist_id']})",
        f"OpenAlex works fetched: {report['total_works']}",
        f"Works matching watchlist: {report['matched_watchlist_works']}",
        f"New researchers added: {len(report['added'])}",
        f"Existing researchers updated: {report['updated_existing']}",
        f"Paper records appended: {report['paper_updates']}",
        f"Industrial members added: {report['team_member_additions']}",
        f"Industrial member records updated: {report['team_member_updates']}",
        f"Industrial teams touched: {report['team_entries_touched']}",
        f"Matched papers: {report['matched_papers']}",
        f"Skipped by relevance score: {report['skipped_due_to_score']}",
        f"Skipped by venue: {report['skipped_due_to_venue']}",
        f"Skipped by focus filter: {report['skipped_due_to_focus']}",
        f"Skipped by institution matching: {report['skipped_due_to_match']}",
        f"Skipped by author-role guardrail: {report['skipped_due_to_role']}",
    ]
    if report["added"]:
        lines.append("Added researchers:")
        for entry in report["added"]:
            inst_label = entry.get("institution_display_name") or entry["institution"]
            lines.append(f"  - {entry['name']} ({inst_label})")
    if report.get("report_paths"):
        lines.append("Reports written:")
        for path in report["report_paths"]:
            lines.append(f"  - {path}")
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
        "--watchlist",
        default="",
        help="Which literature watchlist to use from data/literature_watchlists.json",
    )
    parser.add_argument(
        "--list-watchlists",
        action="store_true",
        help="Print available watchlists and exit",
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
    parser.add_argument(
        "--member-lookback-days",
        type=int,
        default=DEFAULT_MEMBER_LOOKBACK_DAYS,
        help="How many days back to scan for industrial team members (default: 180)",
    )
    parser.add_argument(
        "--report-dir",
        default="",
        help="Directory for markdown literature reports, relative to repo root unless absolute",
    )
    parser.add_argument(
        "--archive-report",
        action="store_true",
        help="Also write a dated markdown report alongside latest.md",
    )
    parser.add_argument(
        "--skip-empty-report",
        action="store_true",
        help="Do not write a markdown report when the run produced no matched papers or site updates",
    )
    parser.add_argument(
        "--report-limit",
        type=int,
        default=DEFAULT_REPORT_LIMIT,
        help="Maximum number of matched papers to include in the markdown report",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    watchlists_payload = load_watchlists()
    if args.list_watchlists:
        default_watchlist = watchlists_payload["default_watchlist"]
        for watchlist_id, meta in sorted(watchlists_payload["watchlists"].items()):
            default_marker = " (default)" if watchlist_id == default_watchlist else ""
            print(f"{watchlist_id}{default_marker}: {meta['name']}")
        return 0

    requested_watchlist = args.watchlist.strip() or watchlists_payload["default_watchlist"]
    watchlist = resolve_watchlist(watchlists_payload, requested_watchlist)
    data = load_researchers()
    institutions = load_institutions()
    qs_rankings = load_qs_rankings()

    today = date.today().isoformat()
    start_date = (date.fromisoformat(today) - timedelta(days=args.lookback_days)).isoformat()
    member_lookback_days = max(args.lookback_days, args.member_lookback_days)

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "ai4db-teams-discovery/1.0 (+https://github.com/lyntele/ai4db-teams)",
        }
    )
    search_terms = watchlist.get("search_terms") or SEARCH_TERMS
    works = collect_works(session, start_date=start_date, end_date=today, search_terms=search_terms)
    filtered_works, filter_report = filter_works_for_watchlist(works, watchlist)
    report = discover(data, institutions, qs_rankings, filtered_works, today)
    if member_lookback_days == args.lookback_days:
        member_works = filtered_works
    else:
        member_start_date = (date.fromisoformat(today) - timedelta(days=member_lookback_days)).isoformat()
        raw_member_works = collect_works(
            session,
            start_date=member_start_date,
            end_date=today,
            search_terms=search_terms,
        )
        member_works, _member_filter_report = filter_works_for_watchlist(raw_member_works, watchlist)
    member_report = refresh_industry_team_members(data, institutions, member_works, today)
    report.update(member_report)
    report.update(filter_report)
    report["total_works"] = filter_report["fetched_works"]
    report["watchlist_id"] = watchlist["id"]
    report["watchlist_name"] = watchlist["name"]

    report_paths: List[str] = []
    if args.report_dir.strip():
        report_dir = Path(args.report_dir)
        if not report_dir.is_absolute():
            report_dir = ROOT_DIR / report_dir
        written_reports = write_watchlist_report(
            output_dir=report_dir,
            watchlist=watchlist,
            raw_stats=filter_report,
            filtered_works=filtered_works,
            report=report,
            start_date=start_date,
            end_date=today,
            report_limit=max(args.report_limit, 1),
            archive=args.archive_report,
            skip_empty=args.skip_empty_report,
        )
        report_paths = [str(path) for path in written_reports]
    report["report_paths"] = report_paths

    print(summarize(report))

    if args.apply and not args.dry_run and (
        report["paper_updates"] > 0
        or report["team_member_additions"] > 0
        or report["team_member_updates"] > 0
    ):
        save_researchers(data)
        print(f"Saved updates to {ROOT_DIR / 'data' / 'researchers.json'}")
    else:
        print("Dry run only. data/researchers.json was not written.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
