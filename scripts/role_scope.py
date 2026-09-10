"""Candidate retention only. dbt applies the same versioned seed to classify rows."""
import csv
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
RULES = list(csv.DictReader((ROOT / 'seeds/role_patterns.csv').open(encoding='utf-8')))


def is_candidate(ad):
    title = (ad.get('headline') or '').lower()
    raw = ad.get('occupation') or {}
    if isinstance(raw, list):
        raw = next((item for item in raw if item.get('original_value')), raw[0] if raw else {})
    occupation = (raw.get('label') or '').lower()
    return any(re.search(r['title_pattern'], title) or re.search(r['taxonomy_pattern'], occupation)
               for r in RULES)
