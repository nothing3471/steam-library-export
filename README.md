# steam-library-export

**Steam has no export button.** The library page is a virtualised list — scroll
away from a game and its row stops existing, so select-all-and-copy gets you a
handful of rows and a lot of whitespace. Third-party sites want your login.

This is a single Python file that pulls your whole library through Steam's own
Web API and writes it to disk.

```
python steam_library.py your_vanity_name
```

Three files land in the current directory:

| File | What it is |
|---|---|
| `steam_library.csv` | one row per game — appid, name, hours (total, 2-week, per-platform), last played, store URL |
| `steam_library_report.md` | readable report: account summary, playtime distribution, top 50, full library |
| `steam_library_raw.json` | the untouched API responses, so you can re-process without re-fetching |

## Setup

Python 3.7 or newer. **No dependencies** — standard library only.

You need a Steam Web API key, which is free and takes about thirty seconds:
[steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey). Any
domain works; put `localhost` if the form insists.

```bash
export STEAM_API_KEY=xxxxxxxxxxxx     # or let it prompt you
python steam_library.py your_vanity_name
```

Your vanity name is the last part of your profile URL —
`steamcommunity.com/id/`**`this_bit`**`/`. If your URL looks like
`/profiles/76561198…` instead, pass that 17-digit number directly.

```bash
python steam_library.py 76561198000000000
python steam_library.py your_name --out ~/exports
```

The key is only ever sent to `api.steampowered.com` over HTTPS. It is not
written to any of the output files.

## Two things that will bite you

**"The API returned zero games."** Your library is private. Steam → Profile →
Edit Profile → Privacy Settings → set **Game details** to Public. You can set it
back afterwards. This is by far the most common problem and the script says so
rather than silently writing an empty CSV.

**The output contains personal data.** `steam_library_report.md` includes your
SteamID64, profile URL, country and every game you own with hours played. That
is why output goes to your working directory instead of next to the script, and
why the bundled `.gitignore` excludes all three files. Check before you share
one.

## Notes

Playtime is reported by Steam in minutes and converted here; games played before
Steam started tracking hours (roughly pre-2009) may read as 0. `last_played`
comes from `rtime_last_played`, which is not set for games you have never
launched. Free games you have "played" appear; ones you have only ever installed
may not.

Retries on HTTP 429 and 5xx with a widening backoff. A 401 or 403 stops
immediately, because that means the key is wrong and retrying will not help.

## Licence

MIT. See [LICENSE](LICENSE).
