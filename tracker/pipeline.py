"""One input read, shared by the continuous server and cron publisher."""
from datetime import datetime
from pathlib import Path
from .sources import read_google


def poll_once(store, source, log=None, doc_id=None, token_path=None, expected_interval=15):
    store.set_health(last_attempt=datetime.now().astimezone().isoformat(),mode=source,
                     expected_interval_seconds=expected_interval)
    try:
        text = Path(log).read_text(encoding='utf-8-sig') if source=='file' else read_google(doc_id,token_path)
        if len(text)>5_000_000:
            raise ValueError('Input exceeds the five-megabyte limit')
        store.ingest(text)
        store.set_health(last_success=datetime.now().astimezone().isoformat(),error=None)
        return True
    except Exception as exc:
        message = str(exc) if isinstance(exc,(ValueError,FileNotFoundError)) else f'Could not read {source} input ({type(exc).__name__}). Check internet access and sharing.'
        store.set_health(error=message)
        return False
