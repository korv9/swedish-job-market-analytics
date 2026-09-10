"""Render the exported aggregates as a standalone report preview (not a Power BI screenshot)."""
import argparse
import base64
import csv
from datetime import datetime
from html import escape
from pathlib import Path
import os

os.environ.setdefault('MPLCONFIGDIR', str(Path(__file__).resolve().parents[1]/'data/matplotlib'))

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def read(path):
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


def plot_report(jobs, skills, comparison, name, destination):
    if name != 'All roles':
        jobs = [r for r in jobs if r['role_family'] == name]
        skills = [r for r in skills if r['role_family'] == name]
        comparison = [r for r in comparison if r['role_family'] == name]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
        'axes.spines.right':False,'axes.spines.left':False,'axes.spines.bottom':False})
    fig = plt.figure(figsize=(14, 11), layout='constrained', facecolor='#f7f9fc')
    grid = fig.add_gridspec(3, 2, height_ratios=[0.13,1,1])
    heading = fig.add_subplot(grid[0,:]); heading.axis('off')
    total = sum(int(r['total_ads']) for r in jobs)
    heading.text(0,0.75, f'Swedish job market | {name}', size=21, weight='bold', color='#172b4d')
    heading.text(0,0.1,f'2024–2025 · {total:,} source advertisements · technology mentions, not confirmed requirements',size=11,color='#52627a')
    ax = fig.add_subplot(grid[1,0])
    for role in sorted({r['role_family'] for r in jobs}):
        rows = sorted([r for r in jobs if r['role_family']==role],key=lambda r:r['publication_month'])
        ax.plot([datetime.fromisoformat(r['publication_month']) for r in rows],
            [int(r['total_ads']) for r in rows],marker='o',markersize=3,label=role,linewidth=2)
    ax.set_title('New advertisements per month', loc='left',pad=15,weight='bold')
    ax.set_ylabel('Advertisements'); ax.set_ylim(bottom=0); ax.grid(axis='y',alpha=.15)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.legend(loc='upper left',fontsize=8,frameon=False)
    ax = fig.add_subplot(grid[1,1])
    techs = sorted({r['skill'] for r in skills})
    colors = plt.get_cmap('tab10').colors
    for i,tech in enumerate(techs):
        months = sorted({r['publication_month'] for r in skills})
        values=[]
        for month in months:
            rs=[r for r in skills if r['skill']==tech and r['publication_month']==month]
            denom=sum(int(r['total_ads']) for r in rs)
            values.append(sum(int(r['ads_with_skill']) for r in rs)/denom if denom else float('nan'))
        ax.plot([datetime.fromisoformat(m) for m in months],values,label=tech,color=colors[i],linewidth=1.6)
    ax.set_title('Share mentioning each technology',loc='left',pad=15,weight='bold')
    ax.yaxis.set_major_formatter(PercentFormatter(1)); ax.set_ylim(bottom=0); ax.grid(axis='y',alpha=.15)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=4)); ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %Y'))
    ax.legend(loc='upper left',bbox_to_anchor=(1,1),frameon=False,fontsize=8)
    ax = fig.add_subplot(grid[2,:])
    changes=[]
    for tech in techs:
        rs=[r for r in comparison if r['skill']==tech]
        b=sum(int(r['baseline_total_ads']) for r in rs); n=sum(int(r['comparison_total_ads']) for r in rs)
        ba=sum(int(r['baseline_skill_ads']) for r in rs); na=sum(int(r['comparison_skill_ads']) for r in rs)
        if b>=20 and n>=20 and max(ba,na)>=5:
            changes.append((tech,100*(na/n-ba/b)))
    changes.sort(key=lambda x:x[1])
    labels=[x[0] for x in changes]; vals=[x[1] for x in changes]
    ax.barh(labels,vals,color=['#247a64' if v>=0 else '#b65357' for v in vals],height=.6)
    ax.axvline(0,color='#7d8795',linewidth=.8); ax.grid(axis='x',alpha=.15)
    ax.set_title('2025 vs 2024 — change in technology share',loc='left',pad=15,weight='bold')
    ax.set_xlabel('Percentage points · minimum 20 cohort ads in each year and 5 mentions in either year')
    span=max([abs(v) for v in vals]+[1]); ax.set_xlim(min(vals+[0])-span*.22,max(vals+[0])+span*.22)
    for i,v in enumerate(vals):
        ax.text(v + (.12 if v>=0 else -.12),i,f'{v:+.1f} pp',va='center',ha='left' if v>=0 else 'right',size=9)
    fig.savefig(destination,dpi=150,bbox_inches='tight')
    plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/powerbi'))
    parser.add_argument('--output',type=Path,default=Path('reports/generated'))
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    jobs,skills,comparison=[read(args.data/f'{n}.csv') for n in ['Jobs','Skills','Comparison']]
    names=['All roles']+sorted({r['role_family'] for r in jobs})
    sections=[]
    for i,name in enumerate(names):
        path=args.output/(name.lower().replace(' ','-')+'.png')
        plot_report(jobs,skills,comparison,name,path)
        image=base64.b64encode(path.read_bytes()).decode()
        sections.append(f'<section id="p{i}" {"hidden" if i else ""}><img alt="Trend charts for {escape(name)}" src="data:image/png;base64,{image}"></section>')
    options=''.join(f'<option value="p{i}">{escape(n)}</option>' for i,n in enumerate(names))
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Swedish job market trends</title>
<style>body{margin:24px;font:16px system-ui;background:#f7f9fc;color:#172b4d}main{max-width:1400px;margin:auto}select{font:inherit;padding:8px}img{width:100%;height:auto}p{max-width:1000px;line-height:1.6}a{color:#175cb5}</style><main>
<label>Role cohort <select onchange="document.querySelectorAll('section').forEach(s=>s.hidden=s.id!==this.value)">'''+options+'''</select></label>
<p>Historical Platsbanken archives, 2024–2025. Counts reflect source advertisement IDs; reposts can occur. Shares measure technology mentions in the selected role cohort. This is a standalone preview of the exported aggregates, not a rendered Power BI report.</p>'''+''.join(sections)+'''<p>Source: <a href="https://data.arbetsformedlingen.se/annonser/historiska/">Arbetsförmedlingen historical archives</a>. See the repository's quality review for coverage, classification and interpretation limits.</p></main></html>'''
    (args.output/'trends.html').write_text(html,encoding='utf-8')
    print(args.output/'trends.html')


if __name__=='__main__':
    main()
