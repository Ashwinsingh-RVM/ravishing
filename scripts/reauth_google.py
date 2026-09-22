"""
Re-mint GOOGLE_REFRESH_TOKEN for the Goa DRS Tracker.

Run this when login fails with:
    Failed to get access token: HTTP 400 {"error": "invalid_grant", ...}

That error means the stored refresh token is dead (expired or revoked). Everything
else about the OAuth setup is still fine - only the token needs replacing.

IMPORTANT: local .env and production use DIFFERENT OAuth clients. A token minted
against one client is rejected by the other with the same invalid_grant error, so
pick the right target:

    python scripts/reauth_google.py            # fixes LOCAL dev (.env)
    python scripts/reauth_google.py --prod     # fixes the LIVE site (Railway)

Needs a browser on this machine. Sign in as the account that owns the tracker sheet.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# Must match SCOPES in src/services/google_services.py exactly. The calendar scope
# is retained for refresh-token compatibility even though Calendar sync was removed.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive",
]

REDIRECT_PORT = 8080


def read_env(path):
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def write_env_value(path, key, value):
    """Replace key's value in .env, preserving every other line and its order."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out, found = [], False
    for line in lines:
        if line.strip() and not line.strip().startswith("#") and "=" in line:
            if line.split("=", 1)[0].strip() == key:
                out.append(f"{key}={value}")
                found = True
                continue
        out.append(line)
    if not found:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def railway_client_creds(service):
    """Read the OAuth client that Railway actually runs with."""
    # shutil.which resolves railway.cmd / railway.exe on Windows; a bare "railway"
    # in an argv list is not found there the way it is from a shell.
    exe = shutil.which("railway")
    if not exe:
        sys.exit("railway CLI not found on PATH. Install it, or pass the client id/secret "
                 "manually via GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET env vars.")
    proc = subprocess.run(
        [exe, "variables", "--service", service, "--json"],
        capture_output=True, text=True, timeout=90,
    )
    if proc.returncode != 0:
        sys.exit("railway variables failed:\n" + proc.stderr.strip())
    env = json.loads(proc.stdout)
    return env["GOOGLE_CLIENT_ID"], env["GOOGLE_CLIENT_SECRET"]


def preflight_redirect(client_id):
    """Fail fast if this OAuth client won't accept our localhost redirect.

    The production client is a *Web* client with only the OAuth Playground
    registered, so run_local_server() dies with redirect_uri_mismatch after the
    user has already sat through a browser flow. Check first and point them at
    the route that actually works.
    """
    params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": f"http://localhost:{REDIRECT_PORT}/",
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    url = "https://accounts.google.com/o/oauth2/auth?" + params
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
    except Exception:
        return  # network hiccup - don't block the real flow

    if "redirect_uri_mismatch" in body.lower():
        sys.exit(
            f"\nThis OAuth client does not allow http://localhost:{REDIRECT_PORT}/ as a\n"
            "redirect URI, so the local browser flow cannot work.\n\n"
            "Use the OAuth Playground instead (already an allowed redirect, no GCP change):\n"
            "  1. https://developers.google.com/oauthplayground\n"
            "  2. Gear icon -> tick 'Use your own OAuth credentials' -> paste the\n"
            f"     client ID and secret for {client_id}\n"
            "  3. Step 1: enter these scopes, then Authorize APIs:\n"
            + "".join(f"       {s}\n" for s in SCOPES) +
            "  4. Step 2: 'Exchange authorization code for tokens' -> copy the refresh token\n"
            "  5. railway variables --service ravishing --set \"GOOGLE_REFRESH_TOKEN=<token>\"\n\n"
            "Alternatively, add the localhost redirect URI to this client in Google Cloud\n"
            "Console -> Credentials, and re-run this script."
        )


def main():
    ap = argparse.ArgumentParser(description="Re-mint GOOGLE_REFRESH_TOKEN.")
    ap.add_argument("--prod", action="store_true",
                    help="mint against the PRODUCTION OAuth client read from Railway "
                         "(required when fixing the live site)")
    ap.add_argument("--service", default="ravishing", help="Railway service name")
    args = ap.parse_args()

    env = read_env(ENV_PATH)
    if args.prod:
        client_id, client_secret = railway_client_creds(args.service)
        print("Minting against the PRODUCTION OAuth client (from Railway).")
    else:
        client_id = os.getenv("GOOGLE_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or env.get("GOOGLE_CLIENT_SECRET")
        print("Minting against the LOCAL OAuth client (.env). Use --prod for the live site.")

    if not client_id or not client_secret:
        sys.exit("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET not found in .env or environment.")

    print(f"OAuth client: {client_id}")
    print("A browser window will open. Sign in as the account that owns the tracker sheet.\n")

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [f"http://localhost:{REDIRECT_PORT}/"],
        }
    }

    preflight_redirect(client_id)

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    # access_type=offline asks for a refresh token; prompt=consent forces Google to
    # actually issue a NEW one. Without prompt=consent, an already-consented client
    # gets back an access token and refresh_token=None - a silent failure.
    creds = flow.run_local_server(
        port=REDIRECT_PORT,
        access_type="offline",
        prompt="consent",
    )

    if not creds.refresh_token:
        sys.exit("No refresh token returned. Re-run - prompt=consent is required to mint one.")

    if args.prod:
        print("\nNew PRODUCTION refresh token minted. Apply it to Railway:\n")
        print(f'    railway variables --service {args.service} '
              f'--set "GOOGLE_REFRESH_TOKEN={creds.refresh_token}"\n')
        print("Railway redeploys automatically after a variable change.")
        print("Local .env was NOT touched - it uses a different OAuth client.")
    else:
        write_env_value(ENV_PATH, "GOOGLE_REFRESH_TOKEN", creds.refresh_token)
        print("\nLocal .env updated. This does NOT affect production;")
        print("re-run with --prod to fix the live site.")


if __name__ == "__main__":
    main()
