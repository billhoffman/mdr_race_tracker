"""Optional private-doc sign-in: python3 -m tracker.google_auth --client-file FILE"""
import argparse
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import urllib.parse
import urllib.request
import webbrowser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-file',type=Path,required=True,help='Google OAuth Desktop app client JSON')
    parser.add_argument('--token-file',type=Path,default=Path('tracker/.secrets/google-token.json'))
    args = parser.parse_args()
    client = json.loads(args.client_file.read_text()).get('installed')
    if not client:
        raise SystemExit('Use an OAuth Desktop app client JSON, not a service-account or web-app key.')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            valid = query.get('state')==[state]
            if valid:
                result.update(code=query.get('code',[None])[0],error=bool(query.get('error')))
            self.send_response(200 if valid else 400)
            self.send_header('Content-Type','text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(b'Authorization received. Return to your terminal.' if valid else b'Invalid authorization state.')
        def log_message(self,*args):
            pass

    with HTTPServer(('127.0.0.1',0),Callback) as server:
        redirect = f'http://127.0.0.1:{server.server_port}/'
        url = 'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode({
            'client_id':client['client_id'],'redirect_uri':redirect,'response_type':'code',
            'scope':'https://www.googleapis.com/auth/documents.readonly',
            'access_type':'offline','prompt':'consent','state':state,
            'code_challenge':challenge,'code_challenge_method':'S256'})
        print('Opening Google sign-in for read-only document access. If needed, open this URL:')
        print(url)
        webbrowser.open(url)
        server.timeout=180
        while not result:
            server.handle_request()
            if not result:
                raise SystemExit('No valid authorization received. Run the helper again to retry.')
    if result.get('error') or not result.get('code'):
        raise SystemExit('Google authorization was not granted.')
    form = urllib.parse.urlencode({'client_id':client['client_id'],'client_secret':client['client_secret'],
        'redirect_uri':redirect,'code':result['code'],'code_verifier':verifier,'grant_type':'authorization_code'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/token',data=form),timeout=20) as response:
            token = json.load(response)
        refresh = token['refresh_token']
    except Exception:
        raise SystemExit('Could not complete Google sign-in. Check the OAuth app settings and retry.')
    args.token_file.parent.mkdir(parents=True,exist_ok=True)
    fd = os.open(args.token_file,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.chmod(args.token_file,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump({'client_id':client['client_id'],'client_secret':client['client_secret'],'refresh_token':refresh},f)
    print(f'Authorization saved locally to {args.token_file}. Do not share this file.')


if __name__=='__main__':
    main()
