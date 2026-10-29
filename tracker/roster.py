"""Additive, atomic roster updates shared by imports and race-day additions."""
import fcntl
import json
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_ROSTER=ROOT/'races/moreau-2026/roster.json'


def validated(runners):
    result={}
    if not isinstance(runners,list):raise ValueError('Roster must be a list of bib/name records')
    for runner in runners:
        bib=str(runner.get('bib','')).strip()
        name=' '.join(str(runner.get('name','')).split())
        if not bib or not name:raise ValueError('Every runner must have a bib and a name')
        if bib in result:raise ValueError('Duplicate bib in roster: '+bib)
        result[bib]={'bib':bib,'name':name}
    return result


def atomic_save(path,data):
    fd,temporary=tempfile.mkstemp(prefix='.roster-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as out:
            out.write(data);out.flush();os.fsync(out.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def update_roster(path,incoming,require_existing=False):
    """Merge additions, preserve missing bibs, refuse reassignment, back up edits.

    Readers see the previous or next complete JSON. A roster lock serializes
    imports/additions, so concurrent registration updates do not lose runners.
    """
    path=Path(path).resolve()
    additions=validated(incoming)
    path.parent.mkdir(parents=True,exist_ok=True)
    with Path(str(path)+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if require_existing and not path.exists():
            raise ValueError('Import the initial UltraSignup roster first; no existing roster at '+str(path))
        old_text=path.read_text() if path.exists() else None
        existing=validated(json.loads(old_text)) if old_text is not None else {}
        changed=[bib for bib,r in additions.items() if bib in existing and existing[bib]['name']!=r['name']]
        if changed:raise ValueError('Existing bib/name assignments changed: '+', '.join(changed)+'. Review the assignment; an existing bib cannot be reassigned by this command.')
        added=[bib for bib in additions if bib not in existing]
        retained=[bib for bib in existing if bib not in additions]
        merged=list((existing|additions).values())
        if old_text is None or added:
            if old_text is not None:atomic_save(Path(str(path)+'.bak'),old_text)
            atomic_save(path,json.dumps(merged,indent=2)+'\n')
        return {'total':len(merged),'added':len(added),'retained':len(retained),'path':str(path)}
