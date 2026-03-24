"""Shared helpers for loading, saving, and validating researcher data."""

import json
import os
from datetime import date

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
RESEARCHERS_PATH = os.path.join(DATA_DIR, 'researchers.json')
INSTITUTIONS_PATH = os.path.join(DATA_DIR, 'institutions.json')

VALID_TYPES = {'faculty', 'industry'}
VALID_CHANCES = {'high', 'medium', 'low', 'internship-only'}
VALID_STATUSES = {
    'considering', 'shortlisted', 'contacted', 'awaiting-reply',
    'applied', 'rejected', 'accepted', 'not-applicable'
}
VALID_PRIORITIES = {'high', 'medium', 'low'}
CONTROLLED_TAGS = {
    'NL2SQL', 'text-to-SQL', 'data-agents', 'LLM-DB',
    'query-optimization', 'table-QA', 'RAG', 'schema-linking',
    'vector-DB', 'knowledge-graph', 'data-integration', 'ML-systems', 'NLP'
}


def load_researchers():
    with open(RESEARCHERS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_researchers(data):
    data['meta']['last_updated'] = date.today().isoformat()
    with open(RESEARCHERS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_institutions():
    with open(INSTITUTIONS_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def next_id(researchers):
    nums = [int(r['id'].split('-')[1]) for r in researchers if r['id'].startswith('uid-')]
    return f"uid-{max(nums) + 1:03d}" if nums else "uid-001"


def validate_entry(entry, institutions):
    errors = []
    if entry.get('type') not in VALID_TYPES:
        errors.append(f"Invalid type: {entry.get('type')}")
    if entry.get('admission_chance') not in VALID_CHANCES:
        errors.append(f"Invalid admission_chance: {entry.get('admission_chance')}")
    if entry.get('application_status') not in VALID_STATUSES:
        errors.append(f"Invalid application_status: {entry.get('application_status')}")
    if entry.get('priority') not in VALID_PRIORITIES:
        errors.append(f"Invalid priority: {entry.get('priority')}")
    if entry.get('institution') and entry['institution'] not in institutions:
        errors.append(f"Unknown institution: {entry['institution']}")
    unknown_tags = set(entry.get('tags', [])) - CONTROLLED_TAGS
    if unknown_tags:
        errors.append(f"Unknown tags: {unknown_tags}")
    return errors
