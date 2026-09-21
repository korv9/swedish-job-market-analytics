"""Run the historical pipeline in dependency order, stopping on the first failure."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-import',action='store_true',help='Use the existing completed historical database')
    parser.add_argument('--years',nargs='+',type=int,default=[2022,2023,2024,2025],
        help='Archive years to import and analyse (default 2022-2025)')
    parser.add_argument('--baseline-year',type=int,help='Baseline year for the skill comparison (default: second newest)')
    parser.add_argument('--comparison-year',type=int,help='Comparison year for the skill comparison (default: newest)')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    env=dict(os.environ,JOB_MARKET_DB=str(root/'data/history.duckdb'),DBT_SEND_ANONYMOUS_USAGE_STATS='false')

    years=sorted(args.years)
    comparison=args.comparison_year or years[-1]
    baseline=args.baseline_year or (years[-2] if len(years) > 1 else years[-1])
    dbt_vars=json.dumps({
        'analysis_start': f'{years[0]}-01-01',
        'analysis_end': f'{years[-1]}-12-01',
        'baseline_year': baseline,
        'comparison_year': comparison,
    })

    steps=[]
    if not args.skip_import:
        steps.append(['scripts/ingest_history.py','--years',*[str(y) for y in years]])
    steps += [
        ['-m','dbt.cli.main','build','--profiles-dir','.','--full-refresh',
         '--target-path','target/history','--log-path','logs/history','--vars',dbt_vars],
        ['-m','dbt.cli.main','docs','generate','--profiles-dir','.',
         '--target-path','target/history','--log-path','logs/history','--vars',dbt_vars],
        ['scripts/export_analytics.py'],
        ['scripts/build_powerbi.py'],
        ['scripts/render_trends.py'],
        ['scripts/export_presentation.py'],
    ]
    for step in steps:
        print('Running: python '+' '.join(step),flush=True)
        subprocess.run([sys.executable,*step],cwd=root,env=env,check=True)


if __name__=='__main__':
    main()
