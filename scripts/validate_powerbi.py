"""Validate PBIR JSON against Microsoft's schemas and resolve local model field bindings."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urldefrag

import jsonschema
import requests
from referencing import Registry, Resource


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path('powerbi'))
    parser.add_argument('--cache',type=Path,default=Path('data/pbir_schema_cache'))
    args=parser.parse_args(); args.cache.mkdir(parents=True,exist_ok=True)

    def retrieve(uri):
        uri=urldefrag(uri)[0]
        # Some Microsoft embedded schemas declare a dotted $id but are hosted at a hyphenated URL.
        uri=uri.replace('schema.embedded.json', 'schema-embedded.json')
        if not uri.startswith('https://developer.microsoft.com/json-schemas/'):
            raise ValueError(f'Unexpected schema host: {uri}')
        path=args.cache/(hashlib.sha256(uri.encode()).hexdigest()+'.json')
        if not path.exists():
            r=requests.get(uri,timeout=60); r.raise_for_status(); path.write_text(r.text,encoding='utf-8')
        return json.loads(path.read_text(encoding='utf-8'))

    count=0
    for path in (args.project/'JobMarket.Report').rglob('*'):
        if path.suffix not in ['.json','.pbir']:
            continue
        data=json.loads(path.read_text(encoding='utf-8'))
        if '$schema' not in data:
            continue
        schema=retrieve(data['$schema'])
        registry=Registry(retrieve=lambda uri: Resource.from_contents(retrieve(uri)))
        jsonschema.validators.validator_for(schema)(schema,registry=registry).validate(data)
        count+=1
    model=json.loads((args.project/'JobMarket.SemanticModel'/'model.bim').read_text(encoding='utf-8'))['model']
    tables={t['name']:t for t in model['tables']}
    for path in (args.project/'JobMarket.Report').rglob('visual.json'):
        data=json.loads(path.read_text(encoding='utf-8'))
        for role in data['visual']['query']['queryState'].values():
            for projection in role['projections']:
                kind,expression=next(iter(projection['field'].items()))
                table=tables[expression['Expression']['SourceRef']['Entity']]
                assert expression['Property'] in {x['name'] for x in table['measures' if kind=='Measure' else 'columns']}
    for rel in model['relationships']:
        for end in ['from','to']:
            assert rel[end+'Column'] in {c['name'] for c in tables[rel[end+'Table']]['columns']}
    print(f'Validated {count} PBIR files, four visual bindings and all model relationships. Desktop rendering/refresh remains unverified.')


if __name__=='__main__':
    main()
