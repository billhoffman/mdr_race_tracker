"""Import bibs and names: python3 -m tracker.import_roster EXPORT --output ROSTER.json"""
import argparse
import csv
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile


def normalize(value):
    return re.sub(r'[^a-z0-9]','',str(value).lower())


def read_rows(path):
    path = Path(path)
    if path.suffix.lower() in {'.csv','.tsv'}:
        with path.open(encoding='utf-8-sig',newline='') as f:
            rows = list(csv.reader(f,delimiter='\t' if path.suffix.lower()=='.tsv' else ','))
    elif path.suffix.lower()=='.xlsx':
        ns = {'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(path) as archive:
            strings = []
            if 'xl/sharedStrings.xml' in archive.namelist():
                strings = [''.join(t.text or '' for t in s.findall('.//m:t',ns)) for s in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si',ns)]
            workbook = ET.fromstring(archive.read('xl/workbook.xml'))
            first = workbook.find('m:sheets/m:sheet',ns)
            relationship = first.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
            links = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
            target = next(item.get('Target') for item in links if item.get('Id')==relationship)
            target = target.lstrip('/') if target.startswith('/') else 'xl/'+target
            rows = []
            for row in ET.fromstring(archive.read(target)).findall('.//m:row',ns):
                values = {}
                for cell in row.findall('m:c',ns):
                    letters = re.match(r'[A-Z]+',cell.get('r'))[0]
                    index = 0
                    for letter in letters:index = index*26+ord(letter)-64
                    value = cell.find('m:v',ns)
                    value = value.text if value is not None else ''.join(t.text or '' for t in cell.findall('.//m:t',ns))
                    if cell.get('t')=='s':value=strings[int(value)]
                    values[index-1] = value or ''
                if values:
                    rows.append([values.get(i,'') for i in range(max(values)+1)])
    else:
        raise ValueError('Use an UltraSignup CSV, TSV or XLSX export')
    rows = [row for row in rows if any(str(v).strip() for v in row)]
    if not rows:
        raise ValueError('Export is empty')
    headers = [normalize(value) for value in rows[0]]
    return [dict(zip(headers,row)) for row in rows[1:]]


def import_roster(path):
    roster, skipped, seen = [], {'no_bib':0,'removed':0,'duplicates':0}, {}
    for number,row in enumerate(read_rows(path),2):
        def value(*keys):
            return next((str(row.get(key,'')).strip() for key in keys if str(row.get(key,'')).strip()),'')
        if value('removed','cancelled','canceled').lower() in {'true','yes','1','y'}:
            skipped['removed'] += 1
            continue
        bib = value('bib','bibnumber','runnumber','runnumber','number')
        if not bib:
            skipped['no_bib'] += 1
            continue
        if re.fullmatch(r'\d+\.0',bib):bib=bib[:-2]
        first, last = value('firstname','first','fn'),value('lastname','last','ln')
        name = ' '.join(p for p in [first,last] if p) or value('name','fullname','participant')
        if not name:
            raise ValueError(f'Row {number}: bib {bib} has no name')
        runner = {'bib':bib,'name':name}
        if bib in seen:
            if seen[bib]!=runner:
                raise ValueError(f'Bib {bib} is assigned to more than one name. Fix the export before importing.')
            skipped['duplicates'] += 1
            continue
        seen[bib] = runner
        roster.append(runner)
    if not roster:
        raise ValueError('No assigned bibs and names found. Assign bib numbers in UltraSignup before exporting.')
    return roster, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    try:
        roster, skipped = import_roster(args.export)
    except (ValueError,KeyError,FileNotFoundError,zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc))
    if args.output.exists():
        old = json.loads(args.output.read_text())
        old_map = {r['bib']:r['name'] for r in old}
        changed = [r['bib'] for r in roster if r['bib'] in old_map and old_map[r['bib']]!=r['name']]
        if changed:
            raise SystemExit('Existing bib/name assignments changed: '+', '.join(changed)+'. Use a new output filename and review before replacing the roster.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(roster,indent=2)+'\n')
    print(f'Imported {len(roster)} runners into {args.output}.')
    print(f'Skipped: {skipped["no_bib"]} without bibs; {skipped["removed"]} removed; {skipped["duplicates"]} duplicate rows.')
    print('Only bib numbers and names were saved; no contact or medical details.')
    print('Restart the tracker after importing. Registration is not confirmation that a runner started.')


if __name__=='__main__':
    main()
