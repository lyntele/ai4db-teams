#!/usr/bin/env python3
"""Interactive CLI to add or update researcher entries."""

import argparse
import sys
from datetime import date

from utils import (
    load_researchers, save_researchers, load_institutions,
    next_id, validate_entry, VALID_TYPES, VALID_CHANCES,
    VALID_STATUSES, VALID_PRIORITIES, CONTROLLED_TAGS,
)


def prompt(label, default='', choices=None):
    suffix = f" [{default}]" if default else ""
    if choices:
        suffix += f" ({'/'.join(choices)})"
    val = input(f"  {label}{suffix}: ").strip()
    if not val:
        return default
    if choices and val not in choices:
        print(f"    Warning: '{val}' not in {choices}")
    return val


def prompt_list(label):
    val = input(f"  {label} (comma-separated): ").strip()
    return [x.strip() for x in val.split(',') if x.strip()] if val else []


def add_new(data, institutions):
    print("\n=== Add New Researcher ===\n")
    today = date.today().isoformat()
    entry = {
        'id': next_id(data['researchers']),
        'name': prompt('Name'),
        'type': prompt('Type', 'faculty', sorted(VALID_TYPES)),
        'institution': prompt('Institution key', '', sorted(institutions.keys())),
        'department': prompt('Department'),
        'country': prompt('Country'),
        'region': prompt('Region', '', ['Asia', 'Europe', 'North America', 'Oceania']),
        'position': prompt('Position'),
        'research_focus': prompt_list('Research focus'),
        'tags': prompt_list(f'Tags {sorted(CONTROLLED_TAGS)}'),
        'homepage': prompt('Homepage URL'),
        'email': prompt('Email'),
        'google_scholar': prompt('Google Scholar URL'),
        'notable_papers': [],
        'research_group_url': prompt('Research group URL'),
        'currently_taking_students': prompt('Taking students?', 'true', ['true', 'false']) == 'true',
        'admission_chance': prompt('Admission chance', 'medium', sorted(VALID_CHANCES)),
        'application_status': prompt('Application status', 'considering', sorted(VALID_STATUSES)),
        'priority': prompt('Priority', 'medium', sorted(VALID_PRIORITIES)),
        'contact_history': [],
        'notes': prompt('Notes'),
        'added_date': today,
        'last_updated': today,
    }

    errors = validate_entry(entry, institutions)
    if errors:
        print(f"\n  Validation warnings: {errors}")

    data['researchers'].append(entry)
    save_researchers(data)
    print(f"\n  Added {entry['name']} as {entry['id']}")


def update_entry(data, uid):
    matches = [r for r in data['researchers'] if r['id'] == uid]
    if not matches:
        print(f"  ID '{uid}' not found.")
        sys.exit(1)
    entry = matches[0]
    print(f"\n=== Update: {entry['name']} ({uid}) ===\n")

    action = prompt('Action', 'contact', ['contact', 'status', 'notes'])
    today = date.today().isoformat()

    if action == 'contact':
        record = {
            'date': today,
            'method': prompt('Method', 'email', ['email', 'wechat', 'in-person', 'other']),
            'notes': prompt('Contact notes'),
        }
        entry['contact_history'].append(record)
        print(f"  Added contact record.")
    elif action == 'status':
        entry['application_status'] = prompt(
            'New status', entry['application_status'], sorted(VALID_STATUSES))
        entry['priority'] = prompt('New priority', entry['priority'], sorted(VALID_PRIORITIES))
    elif action == 'notes':
        entry['notes'] = prompt('New notes', entry['notes'])

    entry['last_updated'] = today
    save_researchers(data)
    print(f"  Updated {entry['name']}.")


def main():
    parser = argparse.ArgumentParser(description='Add or update researcher entries')
    parser.add_argument('--update', metavar='UID', help='Update existing entry by ID (e.g. uid-001)')
    args = parser.parse_args()

    data = load_researchers()
    institutions = load_institutions()

    if args.update:
        update_entry(data, args.update)
    else:
        add_new(data, institutions)


if __name__ == '__main__':
    main()
