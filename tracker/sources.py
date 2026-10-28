"""Document and file input adapters. No dependency on a renderer or report."""
import json
from html.parser import HTMLParser
import re
from .radio import CLOCK, pack_rows
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import time

_TOKENS = {}


def request_text(url, headers=None, allow_html=False):
    request = urllib.request.Request(url,headers={'User-Agent':'MountainDogRaceTracker/0.1',**(headers or {})})
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            content_type = response.headers.get('Content-Type','')
            if 'html' in content_type and not allow_html:
                raise ValueError('Google returned a web/login page instead of document text. Check sharing or use Google sign-in.')
            return response.read(5_000_001).decode('utf-8-sig')
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Google returned HTTP {exc.code}. For public test access, Share > General access > Anyone with the link > Viewer. Otherwise use --google-token.') from exc


def google_token(path):
    """Refresh a local OAuth token; never include secrets in output."""
    path = Path(path)
    cached = _TOKENS.get(str(path))
    if cached and cached[0]>time.time()+60:
        return cached[1]
    credentials = json.loads(path.read_text())
    form = urllib.parse.urlencode({'client_id':credentials['client_id'], 'client_secret':credentials['client_secret'],
        'refresh_token':credentials['refresh_token'],'grant_type':'refresh_token'}).encode()
    request = urllib.request.Request('https://oauth2.googleapis.com/token',data=form)
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            token = json.load(response)
            _TOKENS[str(path)] = (time.time()+token.get('expires_in',3600),token['access_token'])
            return token['access_token']
    except (urllib.error.HTTPError,KeyError) as exc:
        raise ValueError('Google sign-in could not be refreshed. Run the authorization helper again.') from exc


def document_text(document):
    def content(items):
        out = []
        for item in items:
            if 'paragraph' in item:
                out.extend(e.get('textRun',{}).get('content','') for e in item['paragraph'].get('elements',[]))
            if 'table' in item:
                for row in item['table'].get('tableRows',[]):
                    for cell in row.get('tableCells',[]):
                        out.append(content(cell.get('content',[])))
        return ''.join(out)
    tabs = []
    def visit(items):
        for tab in items:
            if 'documentTab' in tab:
                tabs.append(content(tab['documentTab'].get('body',{}).get('content',[])))
            visit(tab.get('childTabs',[]))
    visit(document.get('tabs',[]))
    return '\n'.join(tabs) if tabs else content(document.get('body',{}).get('content',[]))


def read_google(doc_id, token_path=None):
    if token_path:
        data = request_text(f'https://docs.googleapis.com/v1/documents/{doc_id}?includeTabsContent=true',
                            {'Authorization':'Bearer '+google_token(token_path)})
        return document_input(json.loads(data))
    # Public, link-viewable docs are read as HTML to preserve table-cell boundaries.
    # Private docs use the official API above; export access is checked on every poll.
    html = request_text(f'https://docs.google.com/document/d/{doc_id}/export?format=html', allow_html=True)
    return html_input(html)


class ExportHTML(HTMLParser):
    """Extract visible paragraphs and cell boundaries from Google's HTML export."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text=[]; self.rows=[]; self.row=None; self.cell=None; self.hidden=0
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style'}:self.hidden+=1
        if tag=='tr':self.row=[]
        if tag in {'td','th'}:self.cell=[]
        if tag=='br':self.handle_data('\n')
    def handle_data(self, data):
        if self.hidden:return
        self.text.append(data)
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in {'script','style'}:self.hidden=max(0,self.hidden-1)
        if tag=='p':self.handle_data('\n')
        if tag in {'td','th'} and self.cell is not None:
            if self.row is not None:self.row.append(''.join(self.cell).strip())
            self.cell=None
        if tag=='tr' and self.row is not None:
            self.rows.append(self.row);self.row=None


def table_input(rows):
    candidates=[r for r in rows if len(r)==2]
    header=any([c.strip().upper() for c in r]==['TIME','MESSAGE'] for r in candidates)
    timed=any(re.fullmatch(CLOCK,r[0].strip()) for r in candidates)
    if not (header or timed):return None
    return pack_rows([{'time':r[0],'message':r[1]} for r in candidates
                      if [c.strip().upper() for c in r]!=['TIME','MESSAGE']])


def html_input(html):
    parser=ExportHTML();parser.feed(html)
    table=table_input(parser.rows)
    if table is not None:return table
    text=''.join(parser.text)
    if not text.strip() or re.search(r'accounts\.google\.com|ServiceLogin',html,re.I):
        raise ValueError('Google returned a login page instead of the radio document. Check sharing or use Google sign-in.')
    return text


def document_input(document):
    """Preserve two-cell radio rows in the authenticated Docs API path too."""
    rows=[]
    def visit(items):
        for item in items:
            for row in item.get('table',{}).get('tableRows',[]):
                rows.append([document_text({'body':{'content':cell.get('content',[])}}).strip()
                             for cell in row.get('tableCells',[])])
            if 'documentTab' in item:visit(item['documentTab'].get('body',{}).get('content',[]))
            visit(item.get('childTabs',[]))
    visit(document.get('body',{}).get('content',[]))
    visit(document.get('tabs',[]))
    return table_input(rows) or document_text(document)
