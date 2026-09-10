#!/usr/bin/env python3
"""
steam_library.py — pull a complete Steam library report via the Steam Web API.

Outputs three files into the current directory (or --out):
    steam_library.csv          every owned game, one row each
    steam_library_report.md    human-readable report with stats + full list
    steam_library_raw.json     untouched API responses, for re-processing

Usage:
    python steam_library.py your_vanity_name
    python steam_library.py 76561198000000000     # a SteamID64 works too

    export STEAM_API_KEY=xxxxxxxx     # or just run it and paste when prompted

Get a key at https://steamcommunity.com/dev/apikey (any domain works; put
"localhost" if it asks). The key stays on your machine — it is only sent to
api.steampowered.com over HTTPS.

The report contains your SteamID64, profile URL, country and complete library,
so output goes to the working directory rather than next to the script. Running
this inside a clone would otherwise leave your own data sitting in the repo,
one `git add -A` away from being published.
"""

import argparse
import csv
import getpass
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

API = "https://api.steampowered.com"


# ---------------------------------------------------------------- transport

def get_key():
    """Return the API key from $STEAM_API_KEY, or ask for it.

    The prompt does not echo (getpass), so the key stays out of terminal
    scrollback, tmux buffers and screen shares. It is sent only to
    api.steampowered.com and never written to any output file.
    """
    key = os.environ.get("STEAM_API_KEY", "").strip()
    if key:
        return key

    try:
        key = getpass.getpass("Steam Web API key (not shown as you type): ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\nAborted.")
    if not key:
        sys.exit("No API key provided. Get one at https://steamcommunity.com/dev/apikey")
    return key


def call(interface, method, version, key, retries=3, **params):
    """GET an API endpoint, with retry on 429/5xx."""
    params["key"] = key
    params.setdefault("format", "json")
    url = f"{API}/{interface}/{method}/v{version}/?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "steam-library-dump/1.0"})

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401 or e.code == 403:
                sys.exit(f"Steam rejected the key on {interface}/{method} "
                         f"(HTTP {e.code}). Check that the key is correct.")
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                wait = 5 * (attempt + 1)
                print(f"  HTTP {e.code} on {method}, retrying in {wait}s...")
                time.sleep(wait)
                continue
            sys.exit(f"HTTP {e.code} on {interface}/{method}: {e.reason}")
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(5)
                continue
            sys.exit(f"Network error on {interface}/{method}: {e.reason}")
    return {}


# ---------------------------------------------------------------- fetching

def resolve_steamid(key, who):
    # A SteamID64 is 17 digits beginning 7656119. Take one as-is: plenty of
    # accounts have never set a custom URL and have nothing else to give.
    if who.isdigit() and len(who) == 17:
        return who

    data = call("ISteamUser", "ResolveVanityURL", 1, key, vanityurl=who)
    r = data.get("response", {})
    if r.get("success") != 1:
        sys.exit(f"Could not resolve vanity name '{who}'. "
                 f"Steam said: {r.get('message', 'no message')}\n"
                 f"The vanity name is the last part of your profile URL: "
                 f"steamcommunity.com/id/THIS_BIT/ — if your URL looks like "
                 f"/profiles/7656119... instead, pass that number directly.")
    return r["steamid"]


def fetch_all(key, steamid):
    print("Fetching profile summary...")
    summary = call("ISteamUser", "GetPlayerSummaries", 2, key, steamids=steamid)

    print("Fetching Steam level...")
    level = call("IPlayerService", "GetSteamLevel", 1, key, steamid=steamid)

    print("Fetching badges...")
    badges = call("IPlayerService", "GetBadges", 1, key, steamid=steamid)

    print("Fetching owned games (this is the big one)...")
    owned = call("IPlayerService", "GetOwnedGames", 1, key,
                 steamid=steamid,
                 include_appinfo=1,
                 include_played_free_games=1,
                 include_free_sub=1,
                 skip_unvetted_apps=0)

    print("Fetching recently played...")
    recent = call("IPlayerService", "GetRecentlyPlayedGames", 1, key, steamid=steamid)

    return {"summary": summary, "level": level, "badges": badges,
            "owned": owned, "recent": recent}


# ---------------------------------------------------------------- shaping

def hours(minutes):
    return round((minutes or 0) / 60.0, 1)


def ts(epoch):
    if not epoch:
        return ""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def build_rows(owned):
    games = owned.get("response", {}).get("games", [])
    if not games:
        sys.exit("The API returned zero games. Your 'Game details' privacy setting "
                 "is probably not set to Public — change it at "
                 "Steam > Profile > Edit Profile > Privacy Settings.")

    rows = []
    for g in games:
        total = g.get("playtime_forever", 0)
        rows.append({
            "appid": g.get("appid"),
            # `or` not a get() default: Steam returns "name": null for some
            # delisted and unvetted apps, and a default only covers a missing key.
            "name": g.get("name") or f"Unknown app {g.get('appid')}",
            "hours_total": hours(total),
            "minutes_total": total,
            "hours_2weeks": hours(g.get("playtime_2weeks", 0)),
            "hours_windows": hours(g.get("playtime_windows_forever", 0)),
            "hours_mac": hours(g.get("playtime_mac_forever", 0)),
            "hours_linux": hours(g.get("playtime_linux_forever", 0)),
            "hours_deck": hours(g.get("playtime_deck_forever", 0)),
            "last_played": ts(g.get("rtime_last_played")),
            "store_url": f"https://store.steampowered.com/app/{g.get('appid')}/",
        })
    rows.sort(key=lambda r: (-r["minutes_total"], r["name"].lower()))
    return rows


def bucket(rows):
    """Count games per playtime band, working in minutes.

    Steam reports minutes and hours() rounds to one decimal, so a game with one
    or two real minutes becomes 0.0 hours. Bucketing on that rounded value filed
    it under "Never played", which is the one row in this table people actually
    quote. These edges use the raw minutes instead.
    """
    edges = [
        ("Never played (0h)", lambda m: m == 0),
        ("Under 1h", lambda m: 0 < m < 60),
        ("1-5h", lambda m: 60 <= m < 300),
        ("5-10h", lambda m: 300 <= m < 600),
        ("10-25h", lambda m: 600 <= m < 1500),
        ("25-50h", lambda m: 1500 <= m < 3000),
        ("50-100h", lambda m: 3000 <= m < 6000),
        ("100h+", lambda m: m >= 6000),
    ]
    counts = Counter()
    for r in rows:
        for label, test in edges:
            if test(r["minutes_total"]):
                counts[label] += 1
                break
    return [(label, counts.get(label, 0)) for label, _ in edges]


# ---------------------------------------------------------------- output

def md_cell(value):
    """Escape a value for a Markdown table cell.

    An unescaped pipe in a game name adds a column, so the hours and
    last-played values slide out of the row and no renderer complains.
    Steam has titles with pipes in them.
    """
    return str(value).replace("|", "\\|")


def csv_safe(name):
    """Neutralise a leading formula character in a game name.

    Excel and Sheets execute a cell that starts with =, +, - or @, and
    opening the CSV in a spreadsheet is the main thing anyone does with it.
    A leading apostrophe is the standard defence (spreadsheets hide it; a
    text editor will show it).
    """
    return "'" + name if name[:1] in ("=", "+", "-", "@") else name


def write_csv(rows, path):
    fields = ["appid", "name", "hours_total", "hours_2weeks", "last_played",
              "hours_windows", "hours_mac", "hours_linux", "hours_deck", "store_url"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**r, "name": csv_safe(r["name"])})


def write_report(data, rows, steamid, path):
    player = (data["summary"].get("response", {}).get("players") or [{}])[0]
    lvl = data["level"].get("response", {}).get("player_level", "unknown")
    badge_resp = data["badges"].get("response", {})
    recent = data["recent"].get("response", {}).get("games", [])

    # Same reason as bucket(): a game with one minute played is not "never".
    played = [r for r in rows if r["minutes_total"] > 0]
    never = [r for r in rows if r["minutes_total"] == 0]
    total_h = round(sum(r["minutes_total"] for r in rows) / 60.0, 1)

    L = []
    A = L.append
    A(f"# Steam library — {md_cell(player.get('personaname') or steamid)}")
    A("")
    A(f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    A("")
    A("## Account")
    A("")
    A(f"- SteamID64: {steamid}")
    A(f"- Profile: {player.get('profileurl', '')}")
    A(f"- Steam level: {lvl}")
    A(f"- Badges: {len(badge_resp.get('badges', []))}")
    A(f"- Player XP: {badge_resp.get('player_xp', 'unknown')}")
    A(f"- XP to next level: {badge_resp.get('player_xp_needed_to_level_up', 'unknown')}")
    A(f"- Account created: {ts(player.get('timecreated'))}")
    A(f"- Last logoff: {ts(player.get('lastlogoff'))}")
    A(f"- Country: {player.get('loccountrycode', 'not set')}")
    A("")
    A("## Library totals")
    A("")
    A(f"- Games owned: {len(rows):,}")
    A(f"- Games played at least once: {len(played):,} "
      f"({len(played) / len(rows) * 100:.1f}%)")
    A(f"- Never launched: {len(never):,} "
      f"({len(never) / len(rows) * 100:.1f}%)")
    A(f"- Total playtime: {total_h:,.1f} hours ({total_h / 24:,.1f} days)")
    if played:
        A(f"- Mean hours per played game: {total_h / len(played):.1f}")
        # statistics.median averages the two middle values on an even count.
        # Indexing [n // 2] returns the upper one, which is not the median.
        mid = statistics.median(r["hours_total"] for r in played)
        A(f"- Median hours per played game: {mid:.1f}")
    A("")
    A("## Playtime distribution")
    A("")
    A("| Bucket | Games |")
    A("|---|---:|")
    for label, count in bucket(rows):
        A(f"| {label} | {count:,} |")
    A("")

    if recent:
        A("## Played in the last two weeks")
        A("")
        A("| Game | Hours (2wk) | Hours (total) |")
        A("|---|---:|---:|")
        for g in recent:
            A(f"| {md_cell(g.get('name'))} | {hours(g.get('playtime_2weeks'))} "
              f"| {hours(g.get('playtime_forever'))} |")
        A("")

    A("## Top 50 by playtime")
    A("")
    A("| # | Game | Hours | Last played |")
    A("|---:|---|---:|---|")
    for i, r in enumerate(rows[:50], 1):
        A(f"| {i} | {md_cell(r['name'])} | {r['hours_total']} | {r['last_played'] or '—'} |")
    A("")

    A("## Full library, most-played first")
    A("")
    A("| # | AppID | Game | Hours | Last played |")
    A("|---:|---:|---|---:|---|")
    for i, r in enumerate(rows, 1):
        A(f"| {i} | {r['appid']} | {md_cell(r['name'])} | {r['hours_total']} "
          f"| {r['last_played'] or '—'} |")
    A("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------- main

def parse_args():
    p = argparse.ArgumentParser(
        description="Export a complete Steam library to CSV, markdown and raw JSON.",
        epilog="Get an API key at https://steamcommunity.com/dev/apikey",
    )
    p.add_argument(
        "who", nargs="?", default=os.environ.get("STEAM_VANITY", ""),
        help="your Steam vanity name (the last part of steamcommunity.com/id/NAME) "
             "or a 17-digit SteamID64. Defaults to $STEAM_VANITY.",
    )
    p.add_argument(
        "--out", default=".", metavar="DIR",
        help="Directory for the three output files, created if missing. "
             "Existing files of the same name are overwritten. "
             "Defaults to the current directory.",
    )
    args = p.parse_args()
    if not args.who:
        p.error("no account given. Pass your vanity name or SteamID64, "
                "or set STEAM_VANITY.")
    return args


def main():
    args = parse_args()

    # Neither PowerShell nor cmd expands ~ in an argument to a native command,
    # so `--out ~/exports` arrives as the literal string and would otherwise
    # create a folder actually named "~" in the working directory.
    out_dir = os.path.abspath(os.path.expanduser(args.out))
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as e:
        sys.exit(f"Cannot use {out_dir} as the output directory: {e.strerror}")

    key = get_key()
    steamid = resolve_steamid(key, args.who)
    print(f"Resolved {args.who} -> {steamid}")

    data = fetch_all(key, steamid)
    rows = build_rows(data["owned"])

    csv_path = os.path.join(out_dir, "steam_library.csv")
    md_path = os.path.join(out_dir, "steam_library_report.md")
    raw_path = os.path.join(out_dir, "steam_library_raw.json")

    write_csv(rows, csv_path)
    write_report(data, rows, steamid, md_path)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    total_h = sum(r["minutes_total"] for r in rows) / 60.0
    print(f"\n{len(rows):,} games, {total_h:,.1f} hours total.")
    print(f"  {csv_path}")
    print(f"  {md_path}")
    print(f"  {raw_path}")


if __name__ == "__main__":
    main()
