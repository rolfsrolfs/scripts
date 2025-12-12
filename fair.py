#!/usr/bin/env python3
import os, sys, json, time, argparse, hashlib, requests
from datetime import datetime

BASEURL = "https://fairdc.no"

def ts(): return datetime.now().strftime("%Y-%m-%d.%H%M%S")
def userdir(savedir, username): return os.path.join(savedir, username)
def symlink_latest(userdir, ts, name):
    target, link = f"{ts}.{name}", f"latest.{name}"
    try: os.remove(os.path.join(userdir, link))
    except: pass
    os.symlink(target, os.path.join(userdir, link))

def read_json(path): return json.load(open(path))
def write_json(path, data): json.dump(data, open(path, 'w'), indent=2)

def is_token_valid(userdir, verbose):
    try:
        p = os.path.join(userdir, "latest.token.json")
        age = time.time() - os.stat(p).st_mtime
        expires_in = read_json(p)["expires_in"]
        if verbose: print(f"Token age: {int(age)}s < {expires_in}s")
        return age < expires_in
    except: return False

def load_token(userdir, verbose=False):
    try:
        token = read_json(os.path.join(userdir, "latest.token.json"))["access_token"]
        if verbose: print("Loaded existing token")
        return token
    except: return None

def load_password(userdir, verbose=False):
    try:
        return open(os.path.join(userdir, "latest.password.txt")).read().strip()
    except:
        if verbose: print("No latest.password.txt")
        return None

def common_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0',
        'Accept': 'application/json, text/plain, */*', 'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br, zstd', 'DNT': '1', 'Sec-GPC': '1',
        'Connection': 'keep-alive', 'Sec-Fetch-Dest': 'empty', 'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin', 'Priority': 'u=0', 'Pragma': 'no-cache',
        'Cache-Control': 'no-cache', 'TE': 'trailers'
    }

def verbose_dump(resp):
    req = resp.request
    print(f"{req.method} {req.url}\n{req.headers}\n{req.body or ''}\n\n{resp.status_code}\n{resp.text[:500]}...\n")

def api_post(url, data, headers, verbose=False):
    resp = requests.post(url, data=data, headers=headers)
    if verbose: verbose_dump(resp)
    resp.raise_for_status()
    return resp.json()

def api_get(url, headers, verbose=False):
    resp = requests.get(url, headers=headers)
    if verbose: verbose_dump(resp)
    resp.raise_for_status()
    return resp.json()

def get_token(username, pw_hash, userdir, ts, force=False, verbose=False):
    if not force and is_token_valid(userdir, verbose):
        return load_token(userdir, verbose)
    
    headers = {**common_headers(), 
               'Content-Type': 'application/x-www-form-urlencoded',
               'Authorization': 'Bearer null', 'Origin': BASEURL,
               'Referer': f'{BASEURL}/dportal/login'}
    
    data = f"username={username}&password={pw_hash}&grant_type=password&AppID=dp&company=FDC%5Cfdcapi"
    token_data = api_post(f"{BASEURL}/dportal/BOXAPI/auth/token", data, headers, verbose)
    
    token_file = os.path.join(userdir, f"{ts}.token.json")
    write_json(token_file, token_data)
    symlink_latest(userdir, ts, "token.json")
    return token_data["access_token"]

def fetch_data(path, token, userdir, ts, name, verbose=False):
    headers = {**common_headers(), 'Authorization': f'Bearer {token}', 'Referer': f'{BASEURL}/dportal/login'}
    data = api_get(f"{BASEURL}{path}", headers, verbose)
    
    out_file = os.path.join(userdir, f"{ts}.{name}")
    write_json(out_file, data)
    symlink_latest(userdir, ts, name)

def main():
    parser = argparse.ArgumentParser(description="FairDC API fetcher")
    parser.add_argument("username", nargs="?", help="Username (case number)")
    parser.add_argument("password", nargs="?", help="Password (if provided)")
    parser.add_argument("-s", type=int, choices=[0,1,2], default=0, help="Stop level: 0=all, 1=after token, 2=after cases")
    parser.add_argument("-S", type=int, choices=[1,2,3], help="Single step: 1=token, 2=cases, 3=timeline")
    parser.add_argument("-a", "--auth", action="store_true", help="Force re-authentication")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose debug output")
    parser.add_argument("--savedir", default=os.path.expanduser("~/fairdc"), help="Save directory")

    args = parser.parse_args()
    
    if not args.username: print("Error: username required"); return 1
    if args.S and args.s: print("Error: -s/-S exclusive"); return 1
    
    ts_ = ts()
    savedir = os.path.expanduser(args.savedir)
    userdir = userdir(savedir, args.username)
    os.makedirs(userdir, exist_ok=True)
    
    # Password handling
    pw_file = os.path.join(userdir, f"{ts_}.password.txt")
    lpw_file = os.path.join(userdir, "latest.password.txt")
    if args.password:
        with open(pw_file, "w") as f: f.write(args.password)
        symlink_latest(userdir, ts_, "password.txt")
    
    password = load_password(userdir)
    if not password: print("Error: no password.txt"); return 1
    
    pw_hash = hashlib.md5(password.encode()).hexdigest()
    token = None
    
    # Determine steps
    steps = [args.S] if args.S else [1,2,3][:args.s+1] if args.s else [1,2,3]
    
    try:
        for step in steps:
            if step == 1:
                token = get_token(args.username, pw_hash, userdir, ts_, args.auth, args.verbose)
            elif step in [2,3] and not token:
                token = load_token(userdir, args.verbose)
                if not token:
                    print("No token!")
                    continue                
                #token = load_token(userdir, args.verbose) or (print("No token!"); continue)
            
            if step == 2: fetch_data("/dportal/BOXAPI/api/debtorportal/cases", token, userdir, ts_, "cases.json", args.verbose)
            if step == 3: fetch_data("/dportal/BOXAPI/api/debtorportal/timeline", token, userdir, ts_, "timeline.json", args.verbose)
            
        if args.verbose: print("Done!")
    except Exception as e: print(f"Error: {e}"); return 1

if __name__ == "__main__": sys.exit(main())
