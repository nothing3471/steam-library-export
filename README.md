# steam-library-export

Steam will not export your library and you cannot copy-paste it out. The library
page is virtualised — scroll past a game and its row stops existing — so select-all
gets you whatever happened to be on screen and a lot of whitespace.

This is one Python file. It asks Steam's own Web API for the library and writes it
to disk. It only reads. It never touches your account.

```
python steam_library.py your_vanity_name
```

Three files land in whatever directory you ran it from:

| File | Contents |
|---|---|
| `steam_library.csv` | one row per game: appid, name, hours total, hours in the last fortnight, hours per platform, last played, store URL |
| `steam_library_report.md` | account summary, playtime buckets, top 50, then everything, most-played first |
| `steam_library_raw.json` | the raw API responses, so changing your mind about the output costs nothing |

## Getting it

One file. Clone the repo, or just download `steam_library.py` on its own and run it
wherever you like — it imports nothing outside the standard library and needs no
other file in the repo.

```bash
git clone https://github.com/nothing3471/steam-library-export
cd steam-library-export
```

## What it needs

Python 3.7 or newer. No dependencies.

A Steam Web API key, free, about a minute to get:
[steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey). Any domain
works (put `localhost` if the form insists on one).

```powershell
$env:STEAM_API_KEY = "xxxxxxxxxxxx"    # PowerShell
set STEAM_API_KEY=xxxxxxxxxxxx         # cmd
export STEAM_API_KEY=xxxxxxxxxxxx      # bash
```

Leave it unset and the script asks for it. The prompt does not echo, so the key
stays out of your scrollback. It is sent to `api.steampowered.com` and nowhere else,
and it is never written into any of the three output files.

```bash
python steam_library.py your_vanity_name
```

Your vanity name is the last part of your profile URL. If yours reads
`/profiles/76561198…` you never set one — pass that 17-digit number instead and the
lookup is skipped.

## Two things that will bite you

**Zero games returned.** Your library is private, which is the default. Steam →
Profile → Edit Profile → Privacy Settings → Game details → Public. Run it, then set
it back. The script tests for this case and says so rather than writing an empty CSV
and leaving you to work out why.

**The report is personal data.** It carries your SteamID64, profile URL, country,
account creation date and every game you own with hours played. Output goes to your
working directory rather than next to the script, and the bundled `.gitignore`
excludes all three files by name. Without both of those, running this inside a clone
leaves your library one `git add -A` from being public. Read the report before you
share it.

## Numbers that lie

Playtime arrives in minutes. Anything played before Steam tracked hours — roughly
pre-2009 — can read as 0 despite hundreds of real ones.

`last_played` is absent for games you never launched, so a blank there means
never, not unknown.

## When it gives up

Three attempts total: the first, then retries five and ten seconds later. Only 429,
500, 502 and 503 are retried — every other status, 504 included, stops on the first
response.

401 and 403 stop immediately. The key is wrong, and the API is not going to change
its mind about that.

## Licence

MIT. See [LICENSE](LICENSE).
