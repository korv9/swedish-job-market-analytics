"""Export aggregated, validated dbt marts and review samples for local reporting."""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def export_table(con, sql, destination):
    cursor = con.execute(sql)
    columns = [{'name': c[0], 'type': str(c[1])} for c in cursor.description]
    rows = cursor.fetchall()
    with destination.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([c['name'] for c in columns])
        writer.writerows(rows)
    return {'file': destination.name, 'rows': len(rows), 'columns': columns,
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default='data/history.duckdb')
    parser.add_argument('--output', type=Path, default=Path('data/powerbi'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(args.database, read_only=True) as con:
        missing = con.execute('''select count(*) from analytics_marts.mart_job_trends_monthly
            where not is_complete''').fetchone()[0]
        if missing:
            raise ValueError(f'{missing} role-months have incomplete archive coverage; export aborted')
        versions = {r[0] for r in con.execute('select distinct scope_version from raw.collection_coverage').fetchall()}
        if versions != {hashlib.sha256((ROOT/'seeds/role_patterns.csv').read_bytes()).hexdigest()}:
            raise ValueError('Candidate rules changed; reprocess archives before publishing analysis')
        tables = {
            'Jobs': 'select * from analytics_marts.mart_job_trends_monthly order by publication_month, role_family',
            'Skills': 'select * from analytics_marts.mart_skill_trends_monthly order by publication_month, role_family, skill',
            'Comparison': 'select * from analytics_marts.mart_skill_year_comparison order by role_family, skill',
            'Roles': 'select distinct role_family from analytics_marts.mart_job_trends_monthly order by 1',
            'Months': 'select distinct publication_month from analytics_marts.mart_job_trends_monthly order by 1'
        }
        manifest = {'database': str(Path(args.database).resolve()),
                    'generated_at': datetime.now(timezone.utc).isoformat(), 'tables': {}}
        for name, sql in tables.items():
            manifest['tables'][name] = export_table(con, sql, args.output / f'{name}.csv')
        review = args.output.parent / 'quality'
        review.mkdir(exist_ok=True)
        export_table(con, '''select job_id, title, occupation, occupation_field_id, role_family,
            classification_basis, role_match_count, published_at,
            left(description, 600) as description_excerpt
            from analytics_intermediate.int_job_ads_enriched
            qualify row_number() over (partition by role_family, classification_basis order by md5(job_id)) <= 12
            order by role_family, classification_basis, job_id''', review/'role_review.csv')
        export_table(con, '''select s.skill, j.job_id, j.title,
            regexp_extract(lower(j.description), '.{0,100}' || p.pattern || '.{0,100}', 0) as match_context
            from analytics_marts.bridge_job_skills s
            join analytics_intermediate.int_job_ads_enriched j using(job_id)
            join analytics.technology_patterns p using(skill)
            where j.role_family <> 'Other'
            qualify row_number() over (partition by skill order by md5(job_id)) <= 8
            order by skill, job_id''', review/'skill_review.csv')
        export_table(con, '''select md5(lower(title) || coalesce(employer_id,'') || description) as content_key,
            count(*) as ad_count, min(published_at) as first_publication, max(published_at) as last_publication
            from analytics_intermediate.int_job_ads_enriched
            where role_family <> 'Other'
            group by 1 having count(*) > 1 order by ad_count desc''', review/'possible_reposts.csv')
        quality = {
            'raw_versions': con.execute('select count(*) from raw.job_ads').fetchone()[0],
            'unique_ads': con.execute('select count(*) from analytics_marts.fct_job_ads').fetchone()[0],
            'role_counts': con.execute('select role_family,count(*) from analytics_marts.fct_job_ads group by 1 order by 1').fetchall(),
            'classification_counts': con.execute('select classification_basis,count(*) from analytics_marts.fct_job_ads group by 1 order by 1').fetchall(),
            'year_role_counts': con.execute('''select year(published_at),role_family,count(*) from analytics_marts.fct_job_ads
                where role_family <> 'Other' group by 1,2 order by 1,2''').fetchall(),
            'coverage': con.execute('select publication_month,status,source_rows,candidate_rows from raw.collection_coverage order by 1').fetchall(),
            'missing_descriptions': con.execute("select count(*) from analytics_intermediate.int_job_ads_enriched where description='' and role_family <> 'Other'").fetchone()[0],
            'duplicate_original_ids': con.execute('''select count(*) from (select original_id from analytics_staging.stg_job_ads
                where original_id is not null group by 1 having count(*) > 1)''').fetchone()[0]
        }
        (review/'summary.json').write_text(json.dumps(quality, indent=2, default=str), encoding='utf-8')
    (args.output/'export_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps({k:v['rows'] for k,v in manifest['tables'].items()}))


if __name__ == '__main__':
    main()
