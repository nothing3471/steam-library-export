# steam-library-export

Steam has no export button, and its library page cannot be copy-pasted into one.
The list is virtualised: scroll away from a game and its row stops existing in the
DOM, so select-all gets you whatever happened to be on screen and a lot of
whitespace. The sites that offer to do it for you want your login.

This is one Python file. It pulls the whole library through Steam's own Web API and
writes it to disk.

```
python steam_library.py your_vanity_name
```

Three files land in the working directory:

| File | Contents |
|---|---|
| `steam_library.csv` | one row per game — appid, name, hours total, hours in the last two weeks, hours per platform, last played, store URL |
| `steam_library_report.md` | account summary, playtime distribution, top 50, then the full library most-played first |
| `steam_library_raw.json` | the untouched API responses, so a change of mind about the shaping does not cost another fetch |

## Setup

Python 3.7 or newer, standard library only. There is nothing to install.

You need a Steam Web API key. It is free and takes about thirty seconds:
[steamcommunity.com/dev/apikey](https://steamcommunity.com/dev/apikey). Any domain
works — put `localhost` if the form insists on one.

```bash
export STEAM_API_KEY=xxxxxxxxxxxx     # or leave it and the script prompts
python steam_library.py your_vanity_name
```

Your vanity name is the last segment of your profile URL:
`steamcommunity.com/id/`**`this_bit`**`/`. If yours reads `/profiles/76561198…`
instead, you have never set one — pass that 17-digit number directly and the script
skips the lookup.

```bash
python steam_library.py 76561198000000000
python steam_library.py your_name --out ~/exports
```

The key goes to `api.steampowered.com` over HTTPS and nowhere else. It is not
written into any of the three output files.

## Two things that will bite you

Stated up front, because both are easier to hit than to diagnose.

**"The API returned zero games."** Your library is private, which is the default.
Steam → Profile → Edit Profile → Privacy Settings → set **Game details** to Public,
run the script, set it back. The script checks for this case and says so rather than
writing an empty CSV and letting you work out why.

**The output is personal data.** `steam_library_report.md` carries your SteamID64,
profile URL, country, account creation date and every game you own with hours
played. That is why the three files go to your working directory rather than next to
the script, and why the bundled `.gitignore` excludes all three by name: running
this inside a clone otherwise leaves your library sitting in a git working tree, one
`git add -A` from being published. Read the report before you share it.

## Numbers that are not what they look like

Playtime comes from Steam in minutes. Anything played before Steam began tracking
hours — roughly pre-2009 — can legitimately read as 0 despite hundreds of real
hours.

`last_played` comes from `rtime_last_played`, which is simply absent for games never
launched, so an empty column there means "never", not "unknown".

Free games appear once played; ones only ever installed may not appear at all. The
owned-games count is therefore Steam's answer to the question, not a philosophical
one.

## Failure behaviour

HTTP 429 and 5xx retry three times with a widening backoff — 5s, then 10s. A 401 or
403 stops immediately and says the key was rejected, because retrying a wrong key
just wastes your time and Valve's.

## Licence

MIT. See [LICENSE](LICENSE).
