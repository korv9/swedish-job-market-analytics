"""Export clean, presentation-ready tables from the historical marts.

Reads data/history.duckdb (the 2022-2025 archive build) and writes tidy,
web-ready CSVs plus a single Excel workbook to data/presentation/. All column
names and labels are in English.

Unlike scripts/export_analytics.py (which emits wide Power BI star-schema CSVs
with technical/NULL columns), this produces flat tables you can publish or open
directly. CSVs are plain UTF-8 (no BOM) so they load cleanly on a website / in
JavaScript CSV parsers; the accompanying .xlsx carries the same data for Excel
users (it stores Swedish characters in region names natively, no encoding caveat).

    python scripts/export_presentation.py

Optional:
    python scripts/export_presentation.py --database data/history.duckdb \
        --output data/presentation --top 15
"""
import argparse
import csv
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]

# The analysed cohort. "Other" is retained in the fact for lineage but excluded
# from every presentation table. Complete archive years are 2022-2025.
FIRST_YEAR, LAST_YEAR = 2022, 2025
YEARS = f"extract(year from published_at) between {FIRST_YEAR} and {LAST_YEAR}"

# Software Developer is far larger than the three data roles, so volume,
# seniority, employer and region tables cover all four; the skill tables stay on
# the data roles because the nine tracked technologies are data-oriented and
# under-represent a general developer's stack.
ALL_ROLES = ("role_family in ('Data Engineer', 'Analytics Engineer', "
             "'Data Scientist', 'Software Developer') and " + YEARS)
DATA_ROLES = ("role_family in ('Data Engineer', 'Analytics Engineer', "
              "'Data Scientist') and " + YEARS)
ROLE_FILTER = ALL_ROLES  # backwards-compatible alias


def write_csv(destination, columns, rows):
    # Plain UTF-8 (no BOM): the web / JS-parser friendly default.
    with destination.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)
    return {'file': destination.name, 'rows': len(rows)}


def q(con, sql, params=None):
    cur = con.execute(sql, params or [])
    return [c[0] for c in cur.description], cur.fetchall()


def build_tables(con, top):
    tables = {}

    # 1. Headline KPIs — one tidy long table of label/value pairs. Framed around
    #    the junior-developer downturn: peak year versus the latest year.
    total = con.execute(
        f"select count(*) from analytics_marts.fct_job_ads where {ALL_ROLES}").fetchone()[0]
    softdev = con.execute(
        f"select count(*) from analytics_marts.fct_job_ads where {ALL_ROLES} "
        "and role_family = 'Software Developer'").fetchone()[0]
    junior = con.execute(
        f"select count(*) from analytics_marts.fct_job_ads where {ALL_ROLES} "
        "and seniority = 'junior'").fetchone()[0]
    employers = con.execute(
        f"select count(distinct employer_id) from analytics_marts.fct_job_ads where {ALL_ROLES}").fetchone()[0]

    # Per-year software-developer and junior-software-developer counts drive the crash KPIs.
    sd_by_year = dict(con.execute(
        f"select extract(year from published_at)::int, count(*) "
        f"from analytics_marts.fct_job_ads where {ALL_ROLES} "
        "and role_family = 'Software Developer' group by 1").fetchall())
    jr_sd_by_year = dict(con.execute(
        f"select extract(year from published_at)::int, count(*) "
        f"from analytics_marts.fct_job_ads where {ALL_ROLES} "
        "and role_family = 'Software Developer' and seniority = 'junior' group by 1").fetchall())

    def peak_to_last(series):
        peak_year = max(series, key=series.get)
        peak, last = series[peak_year], series.get(LAST_YEAR, 0)
        pct = round((last - peak) / peak * 100, 1) if peak else None
        return peak_year, peak, last, pct

    sd_peak_y, sd_peak, sd_last, sd_pct = peak_to_last(sd_by_year)
    jr_peak_y, jr_peak, jr_last, jr_pct = peak_to_last(jr_sd_by_year)
    junior_pct = round(100.0 * junior / total, 1) if total else None
    kpis = [
        (f'Total ads ({FIRST_YEAR}-{LAST_YEAR})', total),
        ('Of which Software Developer', softdev),
        ('Of which data roles (DE/AE/DS)', total - softdev),
        (f'Software Developer {sd_peak_y} (peak)', sd_peak),
        (f'Software Developer {LAST_YEAR}', sd_last),
        (f'Software Developer {LAST_YEAR} vs {sd_peak_y} (%)', sd_pct),
        (f'Junior developers {jr_peak_y} (peak)', jr_peak),
        (f'Junior developers {LAST_YEAR}', jr_last),
        (f'Junior developers {LAST_YEAR} vs {jr_peak_y} (%)', jr_pct),
        ('Junior ads total', junior),
        ('Junior share (%)', junior_pct),
        ('Unique employers', employers),
    ]
    tables['01_overview'] = (['metric', 'value'], kpis)

    # 2. Ads by year and role (all four roles).
    cols, rows = q(con, f"""
        select extract(year from published_at)::int as year,
               role_family as role,
               count(*) as ads,
               count(distinct employer_id) as unique_employers
        from analytics_marts.fct_job_ads
        where {ALL_ROLES}
        group by 1, 2 order by 1, 2
    """)
    tables['02_ads_by_year_role'] = (cols, rows)

    # 3. New ads per month and role (all four roles).
    cols, rows = q(con, """
        select publication_month as month,
               role_family as role,
               observed_ads as new_ads,
               unique_employers
        from analytics_marts.mart_job_trends_monthly
        where is_complete
          and role_family in ('Data Engineer', 'Analytics Engineer',
                              'Data Scientist', 'Software Developer')
        order by publication_month, role_family
    """)
    tables['03_ads_by_month'] = (cols, rows)

    # 4. Seniority by role and year — junior / senior / unspecified counts and shares.
    cols, rows = q(con, f"""
        with base as (
            select role_family, extract(year from published_at)::int as year, seniority,
                   count(*) as n
            from analytics_marts.fct_job_ads where {ALL_ROLES}
            group by 1, 2, 3
        )
        select role_family as role, year,
               sum(n) filter (where seniority = 'junior') as junior,
               sum(n) filter (where seniority = 'senior') as senior,
               sum(n) filter (where seniority = 'unspecified') as unspecified,
               sum(n) as total,
               round(100.0 * sum(n) filter (where seniority = 'junior') / sum(n), 1) as junior_share_pct
        from base group by 1, 2 order by 1, 2
    """)
    tables['04_seniority_by_role_year'] = (cols, rows)

    # 5. Junior ads per month and role — the junior trend over time.
    cols, rows = q(con, f"""
        select date_trunc('month', published_at)::date as month,
               role_family as role,
               count(*) filter (where seniority = 'junior') as junior_ads,
               count(*) as total_ads,
               round(100.0 * count(*) filter (where seniority = 'junior') / count(*), 1) as junior_share_pct
        from analytics_marts.fct_job_ads
        where {ALL_ROLES}
        group by 1, 2 order by 1, 2
    """)
    tables['05_junior_by_month'] = (cols, rows)

    # Cohort split: the general developer stack (Software Developer) vs the data
    # roles. Technology counts now cover both, using the expanded tech dictionary.
    cohort = ("case when role_family = 'Software Developer' then 'Software Developer' "
              "else 'Data roles' end")
    fcohort = cohort.replace('role_family', 'f.role_family')

    # 6. Top technologies per cohort — most-mentioned technologies in the ads.
    cols, rows = q(con, f"""
        with pop as (
            select {cohort} as cohort, count(*) as n
            from analytics_marts.fct_job_ads where {ALL_ROLES} group by 1
        )
        select {fcohort} as cohort,
               b.skill as technology,
               count(distinct b.job_id) as ads_mentioning,
               round(100.0 * count(distinct b.job_id) / p.n, 1) as share_pct
        from analytics_marts.bridge_job_skills b
        join analytics_marts.fct_job_ads f using (job_id)
        join pop p on p.cohort = {fcohort}
        where {ALL_ROLES}
        group by 1, 2, p.n order by 1, 3 desc
    """)
    tables['06_top_technologies'] = (cols, rows)

    # 7. Technology mentions per year and cohort — how each stack shifted over time.
    cols, rows = q(con, f"""
        with pop as (
            select {cohort} as cohort, extract(year from published_at)::int as year, count(*) as n
            from analytics_marts.fct_job_ads where {ALL_ROLES} group by 1, 2
        )
        select {fcohort} as cohort,
               b.skill as technology,
               extract(year from f.published_at)::int as year,
               count(distinct f.job_id) as ads_mentioning,
               round(100.0 * count(distinct f.job_id) / p.n, 1) as share_pct
        from analytics_marts.bridge_job_skills b
        join analytics_marts.fct_job_ads f using (job_id)
        join pop p on p.cohort = {fcohort} and p.year = extract(year from f.published_at)::int
        where {ALL_ROLES}
        group by 1, 2, 3, p.n order by 1, 2, 3
    """)
    tables['07_tech_stack_by_year'] = (cols, rows)

    # 8. Technology share, baseline vs comparison year, per role (all four roles).
    cols, rows = q(con, """
        select role_family as role,
               skill as technology,
               baseline_year,
               comparison_year,
               round(100.0 * baseline_skill_ads / nullif(baseline_total_ads, 0), 1) as share_baseline_pct,
               round(100.0 * comparison_skill_ads / nullif(comparison_total_ads, 0), 1) as share_comparison_pct,
               round(share_change_pp, 1) as change_pp
        from analytics_marts.mart_skill_year_comparison
        where is_complete
        order by role_family, change_pp desc
    """)
    tables['08_skill_change_baseline_vs_comparison'] = (cols, rows)

    # 9. Top employers (all four roles).
    cols, rows = q(con, f"""
        select e.employer_name as employer,
               count(*) as ads
        from analytics_marts.fct_job_ads f
        join analytics_marts.dim_employers e using (employer_id)
        where {ALL_ROLES}
        group by 1 order by 2 desc, 1 limit ?
    """, [top])
    tables['09_top_employers'] = (cols, rows)

    # 10. Ads by region (all four roles).
    cols, rows = q(con, f"""
        select l.region as region,
               count(*) as ads
        from analytics_marts.fct_job_ads f
        join analytics_marts.dim_locations l using (location_id)
        where {ALL_ROLES}
        group by 1 order by 2 desc, 1
    """)
    tables['10_ads_by_region'] = (cols, rows)

    # 11. Full monthly job-trend measures (every metric the mart computes:
    #     month-over-month and year-over-year change, 3-month average, etc.).
    cols, rows = q(con, """
        select publication_month, role_family, observed_ads, total_ads, unique_employers,
               previous_month_ads, previous_year_ads, round(ads_3m_average, 1) as ads_3m_average,
               ads_mom_change, round(100 * ads_mom_pct, 1) as ads_mom_pct,
               ads_yoy_change, round(100 * ads_yoy_pct, 1) as ads_yoy_pct
        from analytics_marts.mart_job_trends_monthly
        where is_complete and role_family <> 'Other'
        order by role_family, publication_month
    """)
    tables['11_job_trends_monthly_full'] = (cols, rows)

    # 12. Full monthly skill-trend measures for all four roles.
    cols, rows = q(con, """
        select publication_month, role_family, skill as technology, total_ads, ads_with_skill,
               round(100 * skill_share, 1) as skill_share_pct,
               round(100 * skill_share_3m, 1) as skill_share_3m_pct,
               sufficient_volume,
               round(100 * skill_ads_yoy_pct, 1) as skill_ads_yoy_pct,
               round(share_yoy_pp, 1) as share_yoy_pp
        from analytics_marts.mart_skill_trends_monthly
        where is_complete
        order by role_family, skill, publication_month
    """)
    tables['12_skill_trends_monthly_full'] = (cols, rows)

    return tables


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', default=str(ROOT / 'data' / 'history.duckdb'))
    parser.add_argument('--output', type=Path, default=ROOT / 'data' / 'presentation')
    parser.add_argument('--top', type=int, default=15, help='Row cap for top-N tables')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(args.database, read_only=True) as con:
        tables = build_tables(con, args.top)

    # Remove stale CSVs from earlier runs so the folder reflects only current tables.
    current = {f'{name}.csv' for name in tables}
    for old in args.output.glob('*.csv'):
        if old.name not in current:
            old.unlink()

    summary = []
    for name, (cols, rows) in tables.items():
        info = write_csv(args.output / f'{name}.csv', cols, rows)
        summary.append(info)
        print(f"{info['file']:<34} {info['rows']:>4} rows")

    # Build a formatted Excel workbook if openpyxl is available.
    try:
        write_workbook(args.output / 'JobMarket_presentation.xlsx', tables)
        print('JobMarket_presentation.xlsx     workbook written')
    except ImportError:
        print('openpyxl not installed; skipped Excel workbook (CSVs written).')

    return summary


SHEET_TITLES = {
    '01_overview': 'Overview',
    '02_ads_by_year_role': 'Ads by year',
    '03_ads_by_month': 'Ads by month',
    '04_seniority_by_role_year': 'Seniority by role',
    '05_junior_by_month': 'Junior by month',
    '06_top_technologies': 'Top technologies',
    '07_tech_stack_by_year': 'Tech stack by year',
    '08_skill_change_baseline_vs_comparison': 'Tech change by year',
    '09_top_employers': 'Top employers',
    '10_ads_by_region': 'Ads by region',
    '11_job_trends_monthly_full': 'All measures jobs',
    '12_skill_trends_monthly_full': 'All measures tech',
}


def write_workbook(destination, tables):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill('solid', fgColor='1F4E5F')
    header_font = Font(color='FFFFFF', bold=True)
    title_font = Font(size=14, bold=True, color='1F4E5F')

    wb = Workbook()
    wb.remove(wb.active)
    for name, (cols, rows) in tables.items():
        ws = wb.create_sheet(SHEET_TITLES.get(name, name)[:31])
        ws.cell(row=1, column=1, value=SHEET_TITLES.get(name, name)).font = title_font
        header_row = 3
        for j, col in enumerate(cols, start=1):
            c = ws.cell(row=header_row, column=j, value=col)
            c.fill = header_fill
            c.font = header_font
            c.alignment = Alignment(horizontal='center')
        for i, row in enumerate(rows, start=header_row + 1):
            for j, val in enumerate(row, start=1):
                ws.cell(row=i, column=j, value=val)
        # Column widths from content.
        for j, col in enumerate(cols, start=1):
            width = max([len(str(col))] + [len(str(r[j - 1])) for r in rows] + [8]) + 2
            ws.column_dimensions[get_column_letter(j)].width = min(width, 42)
        ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    wb.save(destination)


if __name__ == '__main__':
    main()
