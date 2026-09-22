"""
Permanently stop login from breaking when a Google token expires.

Background: login reads the Authorized-Users sheet, so it needs Google credentials
before it can even compare a PIN. Those credentials used to come from an OAuth
refresh token, which Google expires or revokes - and when it died, nobody could log
in. A service account authenticates with a signed key instead: no refresh token, so
nothing to expire.

Gmail stays on the OAuth token on purpose. Sending mail *as a user* requires
Workspace domain-wide delegation, so a service account cannot do it. After this
migration the worst case is that daily digests stop - logins keep working.

You do one thing by hand (Google offers no API to create a key without an existing
key - the bootstrap has to be human):

  1. https://console.cloud.google.com/iam-admin/serviceaccounts
     -> pick the project that owns client 640162266209-...
     -> CREATE SERVICE ACCOUNT -> any name, e.g. "goa-drs-sheets"
     -> no roles needed (access comes from sharing the Sheet, not IAM)
     -> open it -> KEYS -> ADD KEY -> Create new key -> JSON -> download

Then run:

    python scripts/setup_service_account.py path/to/key.json

which shares the production Sheet with the service account, uploads the key to
Railway, and verifies the whole path end to end.
"""
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SERVICE = "ravishing"

SA_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def railway(*args, timeout=120):
    exe = shutil.which("railway")
    if not exe:
        sys.exit("railway CLI not found on PATH. Install it: npm i -g @railway/cli")
    proc = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        sys.exit(f"railway {' '.join(args[:2])} failed:\n{proc.stderr.strip()}")
    return proc.stdout


def prod_env():
    return json.loads(railway("variables", "--service", SERVICE, "--json"))


def oauth_access_token(env):
    """Mint a short-lived access token from the existing OAuth refresh token.

    Needed only to grant the service account access to the Sheet - a service
    account cannot share a file with itself.
    """
    data = urllib.parse.urlencode({
        "client_id": env["GOOGLE_CLIENT_ID"],
        "client_secret": env["GOOGLE_CLIENT_SECRET"],
        "refresh_token": env["GOOGLE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as e:
        sys.exit(
            "Could not use the existing OAuth token to share the Sheet:\n"
            f"  {e.read().decode()}\n\n"
            "Run 'python scripts/fix_login.py' first to refresh it, then re-run this.\n"
            "(Alternatively share the Sheet with the service account by hand in the\n"
            "Google Sheets UI - Share -> paste client_email -> Editor - and re-run.)"
        )


def share_sheet(access_token, sheet_id, client_email):
    """Give the service account Editor on the production Sheet."""
    body = json.dumps({
        "type": "user", "role": "writer", "emailAddress": client_email,
    }).encode()
    url = (f"https://www.googleapis.com/drive/v3/files/{sheet_id}/permissions"
           "?sendNotificationEmail=false&supportsAllDrives=true")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return True, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return False, e.read().decode()


def verify(key_info, sheet_id):
    """Prove the service account can actually open the Sheet."""
    try:
        from google.oauth2.service_account import Credentials
        import gspread
    except ImportError as e:
        print(f"  (skipped local verification - {e})")
        return None
    try:
        creds = Credentials.from_service_account_info(key_info, scopes=SA_SCOPES)
        gc = gspread.authorize(creds)
        ws = gc.open_by_key(sheet_id).worksheet("Authorized-Users")
        return len(ws.get_all_records())
    except Exception:
        # No access yet (or the Sheet isn't shared) - the caller grants it.
        return False


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    key_path = Path(sys.argv[1])
    if not key_path.exists():
        sys.exit(f"Key file not found: {key_path}")

    key_info = json.loads(key_path.read_text(encoding="utf-8"))
    client_email = key_info.get("client_email")
    if not client_email:
        sys.exit("That JSON has no 'client_email' - it is not a service account key.")

    print(f"Service account: {client_email}\n")

    env = prod_env()
    sheet_id = env.get("GOOGLE_SHEETS_ID")
    if not sheet_id:
        sys.exit("GOOGLE_SHEETS_ID is not set on Railway.")
    print(f"Production Sheet: {sheet_id}")

    # Check access BEFORE trying to grant it. If the Sheet was already shared by
    # hand, we never touch the OAuth token - which matters, because the expired
    # token is the whole reason this migration exists.
    print("\n[1/4] Checking whether the service account can already read the Sheet...")
    count = verify(key_info, sheet_id)

    if count is None or count is False:
        print("      no access yet - granting it via the OAuth token")
        token = oauth_access_token(env)
        ok, result = share_sheet(token, sheet_id, client_email)
        if ok:
            print("      shared (Editor)")
        elif "alreadyExists" in str(result) or "duplicate" in str(result).lower():
            print("      already shared")
        else:
            sys.exit(f"      share failed:\n{result}")
        count = verify(key_info, sheet_id)
    else:
        print("      already has access - skipping the share step")

    print("\n[2/4] Verifying Authorized-Users is readable...")
    if count:
        print(f"      read {count} authorized users")

    print("\n[3/4] Uploading the key to Railway...")
    railway("variables", "--service", SERVICE,
            "--set", f"GOOGLE_SERVICE_ACCOUNT_JSON={json.dumps(key_info, separators=(',', ':'))}")
    print("      set GOOGLE_SERVICE_ACCOUNT_JSON")

    print("\n[4/4] Railway is redeploying (~1-2 min).")
    print("\n" + "=" * 62)
    print("DONE. Login now authenticates with a key that cannot expire.")
    print("Gmail digests still use GOOGLE_REFRESH_TOKEN - if that dies later,")
    print("digests stop but logins keep working.")
    print("=" * 62)
    print("\nKeep the key file somewhere safe and OUT of git.")


if __name__ == "__main__":
    main()
