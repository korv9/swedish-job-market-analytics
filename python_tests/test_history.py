import copy
from datetime import date
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import duckdb
import pytest

from scripts.ingest_history import import_archive
from scripts.ingest_jobs import ingest
from scripts.role_scope import is_candidate

ROOT = Path(__file__).resolve().parents[1]


def ad(job_id, published, text='Python', title='Data Engineer'):
    return {'id': job_id, 'headline': title, 'publication_date': published,
            'description': {'text': text}, 'employer': {'name': 'Example', 'organization_number': 'DEMO'},
            'occupation': [{'label': 'Data Scientist', 'original_value': False},
                           {'label': 'Databasutvecklare', 'concept_id': 'rz2m_96d_vyF', 'original_value': True}],
            'occupation_field': [{'concept_id': 'apaJ_2ja_LuF', 'label': 'Data/IT'}]}


def archive(path, rows):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('ads.jsonl', '\n'.join(json.dumps(r) for r in rows))


def test_archive_replay_and_failed_coverage(tmp_path):
    database, file = tmp_path / 'history.duckdb', tmp_path / 'ads.zip'
    rows = [ad('a', '2024-01-15T09:00:00'), ad('b', '2024-02-15T09:00:00', title='Accountant')]
    assert not is_candidate(rows[1])  # secondary taxonomy must not override original value
    archive(file, rows)
    result = import_archive(file, 2024, database)
    assert result['candidate_rows'] == 1
    assert import_archive(file, 2024, database)['new_versions'] == 0
    # A source file year is not a publication-date filter: retain boundary spillovers.
    archive(file, rows + [ad('spillover', '2023-12-22T09:00:00')])
    result = import_archive(file, 2024, database)
    assert result['outside_publication_year'] == 1
    assert result['candidate_rows'] == 2
    with duckdb.connect(str(database)) as con:
        assert con.execute("select count(*) from raw.collection_coverage where status='complete'").fetchone()[0] == 12
    archive(file, [ad('c', '2024-03-01T09:00:00'), ad('bad', 'invalid')])
    with pytest.raises(ValueError):
        import_archive(file, 2024, database, batch_size=1)
    with duckdb.connect(str(database)) as con:
        assert con.execute("select count(*) from raw.collection_coverage where status='complete'").fetchone()[0] == 0


def test_monthly_denominators_zero_missing_and_yoy(tmp_path):
    database = tmp_path / 'trends.duckdb'
    rows = [ad('a', '2024-01-01T10:00:00', 'SQL SQL'), ad('b', '2024-01-02T10:00:00'),
            ad('c', '2025-01-01T10:00:00', 'SQL'), ad('d', '2025-01-02T10:00:00'),
            ad('e', '2025-01-03T10:00:00'), ad('f', '2025-01-04T10:00:00'),
            ad('manager', '2025-01-04T10:00:00', 'SQL', 'Data Engineer Manager'),
            ad('other', '2025-01-04T10:00:00', 'Work with data engineers', 'Accountant')]
    rows[0]['original_id'] = 'same-source-ad'
    duplicate = copy.deepcopy(rows[0]); duplicate['id'] = 'a-second-archive-id'
    rows.append(duplicate)
    # Explicit title wins over an incorrect taxonomy label.
    rows[2]['occupation'] = [{'label': 'Data Scientist', 'original_value': True}]
    rows[2]['headline'] = 'Data Engineer with interest in Analytics Engineering'
    ingest(rows, database, 'historical')
    with duckdb.connect(str(database)) as con:
        for month in ['2024-01-01', '2025-01-01', '2025-02-01']:
            con.execute("insert into raw.collection_coverage (publication_month,status) values (?, 'complete')", [month])
    env = dict(os.environ, JOB_MARKET_DB=str(database), DBT_SEND_ANONYMOUS_USAGE_STATS='false')
    result = subprocess.run([sys.executable, '-m', 'dbt.cli.main', 'build', '--profiles-dir', str(ROOT),
        '--project-dir', str(ROOT), '--target-path', str(tmp_path/'target'), '--log-path', str(tmp_path/'logs')],
        env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    with duckdb.connect(str(database)) as con:
        row = con.execute("""select total_ads, ads_with_skill, skill_share, share_yoy_pp
            from analytics_marts.mart_skill_trends_monthly
            where role_family='Data Engineer' and skill='SQL' and publication_month='2025-01-01'""").fetchone()
        assert row == (4, 1, 0.25, -25.0)
        zero = con.execute("""select total_ads, ads_with_skill, skill_share from analytics_marts.mart_skill_trends_monthly
            where role_family='Data Engineer' and skill='SQL' and publication_month='2025-02-01'""").fetchone()
        assert zero == (0, 0, None)
        missing = con.execute("""select total_ads, ads_with_skill from analytics_marts.mart_skill_trends_monthly
            where role_family='Data Engineer' and skill='SQL' and publication_month='2025-03-01'""").fetchone()
        assert missing == (None, None)
        assert con.execute("select occupation from analytics_staging.stg_job_ads where job_id='historical-original:same-source-ad'").fetchone()[0] == 'Databasutvecklare'
