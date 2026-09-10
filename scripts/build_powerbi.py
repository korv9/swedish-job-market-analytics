"""Generate an editable PBIP/PBIR report over the exported monthly aggregates."""
import argparse
import json
from pathlib import Path
import uuid

SCHEMA = 'https://developer.microsoft.com/json-schemas/fabric/item/report/definition/'


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def field(table, name, measure=False):
    return {'field': {'Measure' if measure else 'Column': {
        'Expression': {'SourceRef': {'Entity': table}}, 'Property': name}},
        'queryRef': f'{table}.{name}', 'active': True}


def visual(root, name, kind, title, position, query):
    formatting = {'title': [{'properties': {
        'show': {'expr': {'Literal': {'Value': 'true'}}},
        'text': {'expr': {'Literal': {'Value': "'"+title.replace("'", "''")+"'"}}}
    }}]}
    write(root/'pages'/'overview'/'visuals'/name/'visual.json', {
        '$schema': SCHEMA+'visualContainer/2.1.0/schema.json', 'name': name,
        'position': dict(zip(['x','y','width','height','z','tabOrder'], position)),
        'visual': {'visualType': kind,
            'query': {'queryState': {k:{'projections':v} for k,v in query.items()}},
            'visualContainerObjects': formatting}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/powerbi'))
    parser.add_argument('--output', type=Path, default=Path('powerbi'))
    args = parser.parse_args()
    manifest = json.loads((args.data/'export_manifest.json').read_text(encoding='utf-8'))
    report = args.output/'JobMarket.Report'
    model = args.output/'JobMarket.SemanticModel'
    write(args.output/'JobMarket.pbip', {'version':'1.0', 'artifacts':[{'report':{'path':'JobMarket.Report'}}],
        'settings':{'enableAutoRecovery':True}})
    write(report/'definition.pbir', {'$schema':'https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json',
        'version':'4.0', 'datasetReference':{'byPath':{'path':'../JobMarket.SemanticModel'}}})
    write(model/'definition.pbism', {'version':'1.0','settings':{}})
    tables = []
    for name, table in manifest['tables'].items():
        columns, transforms = [], []
        for col in table['columns']:
            kind = col['type']
            if kind == 'DATE':
                dtype, mtype = 'dateTime', 'type date'
            elif kind == 'BOOLEAN':
                dtype, mtype = 'boolean', 'type logical'
            elif kind in ['BIGINT','INTEGER','HUGEINT','UBIGINT','SMALLINT']:
                dtype, mtype = 'int64', 'Int64.Type'
            elif kind in ['DOUBLE','FLOAT'] or kind.startswith('DECIMAL'):
                dtype, mtype = 'double', 'type number'
            else:
                dtype, mtype = 'string', 'type text'
            entry = {'name':col['name'],'dataType':dtype,'sourceColumn':col['name'], 'summarizeBy':'none'}
            if kind == 'DATE':
                entry['formatString'] = 'yyyy-MM'
            columns.append(entry)
            transforms.append('{"'+col['name']+'", '+mtype+'}')
        source = ['let', f'    Source = Csv.Document(File.Contents(DataFolder & "/{table["file"]}"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
            '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
            '    Nulls = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),',
            '    Typed = Table.TransformColumnTypes(Nulls, {'+', '.join(transforms)+'}, "en-US")', 'in', '    Typed']
        tables.append({'name':name,'columns':columns,'partitions':[{'name':name,'mode':'import','source':{'type':'m','expression':source}}]})
    measures = {
        'Jobs': [('Ads','SUM(Jobs[total_ads])','#,0')],
        'Skills': [('Technology share','IF(HASONEVALUE(Skills[skill]), DIVIDE(SUM(Skills[ads_with_skill]), SUM(Skills[total_ads])))','0.0%')],
        'Comparison': [('Share change pp',
            'VAR BaseTotal = SUM(Comparison[baseline_total_ads]) VAR NewTotal = SUM(Comparison[comparison_total_ads]) VAR BaseAds = SUM(Comparison[baseline_skill_ads]) VAR NewAds = SUM(Comparison[comparison_skill_ads]) RETURN IF(HASONEVALUE(Comparison[skill]) && BaseTotal >= 20 && NewTotal >= 20 && MAX(BaseAds,NewAds) >= 5, 100 * (DIVIDE(NewAds,NewTotal) - DIVIDE(BaseAds,BaseTotal)))',
            '+0.0;-0.0;0.0')]
    }
    for table in tables:
        if table['name'] in measures:
            table['measures'] = [{'name':n,'expression':e,'formatString':f} for n,e,f in measures[table['name']]]
    relationships = []
    for name in ['Jobs','Skills','Comparison']:
        relationships.append({'name':str(uuid.uuid5(uuid.NAMESPACE_URL,name+'/role')),
            'fromTable':name,'fromColumn':'role_family','toTable':'Roles','toColumn':'role_family',
            'crossFilteringBehavior':'oneDirection'})
    for name in ['Jobs','Skills']:
        relationships.append({'name':str(uuid.uuid5(uuid.NAMESPACE_URL,name+'/month')),
            'fromTable':name,'fromColumn':'publication_month','toTable':'Months','toColumn':'publication_month',
            'crossFilteringBehavior':'oneDirection'})
    folder = str(args.data.resolve()).replace('\\','/').replace('"','""')
    write(model/'model.bim', {'name':'JobMarket','compatibilityLevel':1567,
        'model': {'culture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3',
            'dataAccessOptions':{'legacyRedirects':True,'returnErrorValuesAsNull':True},
            'expressions':[{'name':'DataFolder','kind':'m','expression':'"'+folder+'" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
            'tables':tables,'relationships':relationships}})
    root = report/'definition'
    write(root/'version.json',{'$schema':SCHEMA+'versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    write(root/'report.json',{'$schema':SCHEMA+'report/2.0.0/schema.json','themeCollection':{}})
    write(root/'pages'/'pages.json',{'$schema':SCHEMA+'pagesMetadata/1.0.0/schema.json',
        'pageOrder':['overview'],'activePageName':'overview'})
    write(root/'pages'/'overview'/'page.json',{'$schema':SCHEMA+'page/2.0.0/schema.json',
        'name':'overview','displayName':'Job market | 2024–2025','displayOption':'FitToPage','width':1280,'height':900})
    visual(root,'role_filter','slicer','Role cohort — select one or more', [24,12,1232,90,0,0],
        {'Values':[field('Roles','role_family')]})
    visual(root,'job_volume','lineChart','New advertisements per month', [24,112,600,340,1,1],
        {'Category':[field('Months','publication_month')], 'Y':[field('Jobs','Ads',True)], 'Series':[field('Roles','role_family')]})
    visual(root,'skill_share','lineChart','Technology mentions — share of role advertisements', [648,112,608,340,2,2],
        {'Category':[field('Months','publication_month')], 'Y':[field('Skills','Technology share',True)], 'Series':[field('Skills','skill')]})
    visual(root,'annual_change','clusteredBarChart','2025 vs 2024 — change in technology share (percentage points)', [24,482,1232,390,3,3],
        {'Category':[field('Comparison','skill')], 'Y':[field('Comparison','Share change pp',True)]})
    print(f'Created {args.output / "JobMarket.pbip"}')


if __name__ == '__main__':
    main()
