"""Regression coverage for ingestion and actual dbt incremental behavior."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import duckdb
import pytest

from scripts.ingest_jobs import ingest

ROOT = Path(__file__).resolve().parents[1]
ADS = json.loads((ROOT / 'fixtures/jobs.json').read_text(encoding='utf-8'))


def test_ingestion_replay_update_reversion_and_atomic_validation(tmp_path):
    database = tmp_path / 'test.duckdb'
    assert ingest(ADS + ADS, database, 'fixture') == 4
    assert ingest(ADS, database, 'fixture') == 0
    updated = copy.deepcopy(ADS[0])
    updated['headline'] = 'Updated title'
    assert ingest([updated], database, 'fixture') == 1
    assert ingest([ADS[0]], database, 'fixture') == 1
    with pytest.raises(ValueError):
        ingest([updated, {'headline': 'missing id'}], database, 'fixture')
    with pytest.raises(ValueError):
        ingest(ADS, database, 'live')
    with duckdb.connect(str(database)) as con:
        assert con.execute('select count(*) from raw.job_ads').fetchone()[0] == 6


def test_incremental_matches_full_refresh(tmp_path):
    database = tmp_path / 'integration.duckdb'
    env = dict(os.environ, JOB_MARKET_DB=str(database), DBT_SEND_ANONYMOUS_USAGE_STATS='false')

    def build(*args):
        result = subprocess.run([sys.executable, '-m', 'dbt.cli.main', 'build',
            '--profiles-dir', str(ROOT), '--project-dir', str(ROOT),
            '--target-path', str(tmp_path / 'target'), '--log-path', str(tmp_path / 'logs'),
            *args], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr

    def facts():
        with duckdb.connect(str(database)) as con:
            return con.execute('select * from analytics_marts.fct_job_ads order by job_id').fetchall()

    ingest(ADS, database, 'fixture')
    build()
    initial = facts()
    build()
    assert facts() == initial
    updated = copy.deepcopy(ADS[0])
    updated['headline'] = 'Junior Analytics Engineer'
    updated['employer'] = {'organization_number': 'DEMO-C', 'name': 'Changed Employer'}
    new_ad = copy.deepcopy(ADS[1])
    new_ad['id'] = 'demo-005'
    new_ad['publication_date'] = '2025-01-01T10:00:00'  # late-arriving older publication
    ingest([updated, new_ad], database, 'fixture')
    build()
    incremental = facts()
    assert len(incremental) == 5
    assert incremental[0][4] == 'Junior Analytics Engineer'
    build('--full-refresh')
    assert facts() == incremental
    with duckdb.connect(str(database)) as con:
        assert con.execute("select count(*) from analytics_marts.bridge_job_skills where skill = 'SQL'").fetchone()[0] == 5
