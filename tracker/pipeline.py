"""Independent radio and director reads, shared by server and cron publisher."""
from datetime import datetime
from pathlib import Path
from .sources import read_google


def read_input(source,log,doc_id,token_path):
    text=Path(log).read_text(encoding='utf-8-sig') if source=='file' else read_google(doc_id,token_path)
    if len(text)>5_000_000:raise ValueError('Input exceeds the five-megabyte limit')
    return text


def input_error(exc,source):
    return str(exc) if isinstance(exc,(ValueError,FileNotFoundError)) else f'Could not read {source} input ({type(exc).__name__}). Check internet access and sharing.'


def poll_once(store,source,log=None,doc_id=None,token_path=None,expected_interval=15,
              director_doc_id=None,director_log=None):
    success=True
    # Read director additions first so pending radio bibs can validate this poll.
    if director_doc_id or director_log:
        mode='file' if director_log else 'google'
        health={**store.health.get('director',{}),'last_attempt':datetime.now().astimezone().isoformat(),
                'mode':mode,'expected_interval_seconds':expected_interval}
        try:
            store.ingest_director(read_input(mode,director_log,director_doc_id,token_path))
            health.update(last_success=datetime.now().astimezone().isoformat(),error=None)
        except Exception as exc:
            health['error']=input_error(exc,'director '+mode)
            success=False
        store.set_health(director=health)
    store.set_health(last_attempt=datetime.now().astimezone().isoformat(),mode=source,
                     expected_interval_seconds=expected_interval)
    try:
        store.ingest(read_input(source,log,doc_id,token_path))
        store.set_health(last_success=datetime.now().astimezone().isoformat(),error=None)
    except Exception as exc:
        store.set_health(error=input_error(exc,source))
        success=False
    store.save_review()
    return success
