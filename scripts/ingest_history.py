"""Stream official annual ZIP/JSONL archives, retaining role candidates and coverage."""
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import time
import zipfile

import duckdb
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from .ingest_jobs import ingest
    from .role_scope import is_candidate, ROOT
except ImportError:
    from ingest_jobs import ingest
    from role_scope import is_candidate, ROOT

BASE = 'https://data.arbetsformedlingen.se/annonser/historiska'


def download(year, directory):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'{year}.jsonl.zip'
    url = f'{BASE}/{target.name}'
    if target.exists() and zipfile.is_zipfile(target):
        print(f'Using cached {target}', flush=True)
        return target, url
    partial = target.with_suffix('.zip.part')
    with requests.Session() as session:
        session.mount('https://', HTTPAdapter(max_retries=Retry(total=4, backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504])))
        with session.get(url, stream=True, timeout=(30, 120)) as response:
            response.raise_for_status()
            expected = int(response.headers.get('Content-Length', 0))
            size = 0
            reported = time.monotonic()
            with partial.open('wb') as out:
                for chunk in response.iter_content(1024 * 1024):
                    out.write(chunk)
                    size += len(chunk)
                    if time.monotonic() - reported > 15:
                        print(f'{year}: downloaded {size / 1e6:.0f} MB / {expected / 1e6:.0f} MB', flush=True)
                        reported = time.monotonic()
            if expected and size != expected:
                raise ValueError('Incomplete download')
    if not zipfile.is_zipfile(partial):
        raise ValueError('Download is not a ZIP archive')
    partial.replace(target)
    return target, url


def import_archive(path, year, database, source_uri=None, batch_size=500):
    started = time.monotonic()
    scope_hash = hashlib.sha256((ROOT / 'seeds/role_patterns.csv').read_bytes()).hexdigest()
    with path.open('rb') as handle:
        checksum = hashlib.file_digest(handle, 'sha256').hexdigest()
    ingest([], database, 'historical')
    # Mark every month incomplete before writing. Failed/restarted imports must not publish zeros.
    with duckdb.connect(str(database)) as con:
        for month in range(1, 13):
            con.execute('''insert or replace into raw.collection_coverage values
                (?, ?, ?, 0, 0, null, 'loading', ?)''',
                [date(year, month, 1), source_uri or str(path), checksum, scope_hash])
    counts, candidates = Counter(), Counter()
    batch, added, rows, outside_year = [], 0, 0, 0
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.endswith(('.jsonl', '.ndjson', '.json')) and not n.endswith('/')]
        if not members:
            raise ValueError('No JSONL member in archive')
        for member in members:
            with archive.open(member) as lines:
                for line in lines:
                    if not line.strip():
                        continue
                    ad = json.loads(line)
                    if not isinstance(ad, dict):
                        raise ValueError('Expected one JSON object per line')
                    published = date.fromisoformat(ad['publication_date'][:10])
                    rows += 1
                    if published.year != year:
                        # Preserve spillover candidates: a 2024 ad can occur in the 2025 file.
                        # Its publication date determines analysis membership, never the filename.
                        outside_year += 1
                    key = published.replace(day=1)
                    counts[key] += 1
                    if is_candidate(ad):
                        candidates[key] += 1
                        batch.append(ad)
                    if len(batch) >= batch_size:
                        added += ingest(batch, database, 'historical')
                        batch.clear()
                    if rows % 100000 == 0:
                        print(f'{year}: scanned {rows:,} rows; retained {sum(candidates.values()):,}', flush=True)
    if batch:
        added += ingest(batch, database, 'historical')
    if not rows:
        raise ValueError('Archive contains no ads')
    # Reading to EOF checks ZIP member CRC. Coverage is committed only after the entire archive succeeds.
    with duckdb.connect(str(database)) as con:
        con.execute('begin')
        for month in range(1, 13):
            key = date(year, month, 1)
            con.execute('''update raw.collection_coverage set source_rows=?, candidate_rows=?,
                completed_at=current_timestamp, status='complete' where publication_month=?''',
                [counts[key], candidates[key], key])
        con.execute('commit')
    result = {'year': year, 'source_rows': rows, 'outside_publication_year': outside_year,
              'candidate_rows': sum(candidates.values()),
              'new_versions': added, 'seconds': round(time.monotonic() - started, 2),
              'source_uri': source_uri or str(path), 'sha256': checksum, 'scope_version': scope_hash}
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--years', nargs='+', type=int, default=[2024, 2025])
    parser.add_argument('--database', default='data/history.duckdb')
    parser.add_argument('--directory', type=Path, default=Path('data/history_archives'))
    parser.add_argument('--archive', type=Path, help='Local archive; requires one year')
    args = parser.parse_args()
    if args.archive and len(args.years) != 1:
        parser.error('--archive requires exactly one year')
    results = []
    for year in args.years:
        path, uri = (args.archive, str(args.archive)) if args.archive else download(year, args.directory)
        results.append(import_archive(path, year, args.database, uri))
    args.directory.mkdir(parents=True, exist_ok=True)
    (args.directory / 'last_import.json').write_text(json.dumps(results, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
