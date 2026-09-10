"""Run the historical pipeline in dependency order, stopping on the first failure."""
import argparse
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-import',action='store_true',help='Use the existing completed historical database')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,JOB_MARKET_DB=str(root/'data/history.duckdb'),DBT_SEND_ANONYMOUS_USAGE_STATS='false')
    steps=[]
    if not args.skip_import:
        steps.append(['scripts/ingest_history.py','--years','2024','2025'])
    steps += [
        ['-m','dbt.cli.main','build','--profiles-dir','.', '--full-refresh','--target-path','target/history','--log-path','logs/history'],
        ['-m','dbt.cli.main','docs','generate','--profiles-dir','.', '--target-path','target/history','--log-path','logs/history'],
        ['scripts/export_analytics.py'],
        ['scripts/build_powerbi.py'],
        ['scripts/render_trends.py']
    ]
    for step in steps:
        print('Running: python '+' '.join(step),flush=True)
        subprocess.run([sys.executable,*step],cwd=root,env=env,check=True)


if __name__=='__main__':
    main()
