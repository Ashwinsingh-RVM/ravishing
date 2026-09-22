"""
One-shot fix for "Failed to get access token" on the live Goa DRS Tracker.

What it does, so you don't have to:
  - reads the production OAuth client from Railway
  - opens the Google consent screen in your browser
  - exchanges the code for a fresh refresh token
  - writes it back to Railway
  - verifies the live site can actually get a token again

All you do: sign in, then paste the URL you land on.

    python scripts/fix_login.py

Why the paste step exists: the production OAuth client is a *Web* client, and the
only redirect URI registered on it is the Google OAuth Playground. A Web client
can't hand the code back to a local listener, so the code arrives in your address
bar and has to come back through you. Everything else is automated.
"""
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

SERVICE = "ravishing"
SITE = "https://ravishing-production.up.railway.app/"

# Must match SCOPES in src/services/google_services.py. The calendar scope is kept
# for refresh-token compatibility even though Calendar sync was removed.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]

# The one redirect URI this client actually allows. Verified by probing Google's
# authorize endpoint - localhost, oob and the Railway callback are all rejected.
REDIRECT_URI = "https://developers.google.com/oauthplayground"


def railway(*args, timeout=90):
    exe = shutil.which("railway")
    if not exe:
        sys.exit("railway CLI not found on PATH. Install it first: npm i -g @railway/cli")
    proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        sys.exit(f"railway {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


def get_prod_creds():
    env = json.loads(railway("variables", "--service", SERVICE, "--json"))
    return env["GOOGLE_CLIENT_ID"], env["GOOGLE_CLIENT_SECRET"]


def post_token(payload):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return False, e.read().decode()


def extract_code(pasted):
    """Accept either the whole redirected URL or a bare code."""
    pasted = pasted.strip()
    if not pasted:
        return None
    if "code=" in pasted:
        qs = urllib.parse.urlparse(pasted).query or pasted.split("?", 1)[-1]
        vals = urllib.parse.parse_qs(qs).get("code")
        return vals[0] if vals else None
    return pasted


def main():
    print("Reading production OAuth client from Railway...")
    client_id, client_secret = get_prod_creds()
    print(f"  client: {client_id[:32]}...\n")

    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        # Without prompt=consent an already-consented client returns an access
        # token and refresh_token=None - a silent failure that looks like success.
        "prompt": "consent",
    })

    print("STEP 1  Sign in as the account that owns the tracker sheet.")
    print("        Opening your browser now. If nothing opens, paste this URL:\n")
    print(auth_url + "\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass

    print("STEP 2  After approving, your browser lands on the OAuth Playground page.")
    print("        Copy the FULL URL from the address bar and paste it below.\n")
    pasted = input("Paste URL (or just the code): ")

    code = extract_code(pasted)
    if not code:
        sys.exit("Could not find a 'code' value in what you pasted.")

    print("\nExchanging code for a refresh token...")
    ok, result = post_token({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    })
    if not ok:
        sys.exit(f"Exchange failed:\n{result}\n\n"
                 "An auth code is single-use and expires in ~60s - re-run and paste promptly.")

    refresh_token = result.get("refresh_token")
    if not refresh_token:
        sys.exit("Google returned no refresh token. Re-run - prompt=consent is required.")

    print("Got a refresh token. Writing it to Railway...")
    railway("variables", "--service", SERVICE,
            "--set", f"GOOGLE_REFRESH_TOKEN={refresh_token}", timeout=120)

    print("Verifying the new token works...")
    ok, result = post_token({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    if not ok:
        sys.exit(f"Token was saved but still fails:\n{result}")

    print("\n" + "=" * 60)
    print("DONE - production token is valid again.")
    print("Railway is redeploying (~1-2 min), then log in at:")
    print(f"  {SITE}")
    print("=" * 60)


if __name__ == "__main__":
    main()
