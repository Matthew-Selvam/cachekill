# cachekill

See what is safe to delete on a full disk **before** you delete it.

`cachekill scan` walks your machine's cache directories and classifies every one:

```
SIZE  CLASS  PATH
1.3 GB  SAFE   ~/.bun/install/cache          bun package tarball cache
979 MB  CHECK  ~/Library/Containers/.../vms  Docker VM disk — reclaim INSIDE docker
897 MB  CHECK  ~/Library/Caches/Brave...     Brave HTTP cache — 'Brave Browser' is running
64.8 MB SKIP   ~/Library/Caches/GeoServices  Apple Maps tiles; macOS owns it
```

Three classes, and the discipline is the product:

- **SAFE** — pure regenerable cache (package stores, model weights, browser HTTP
  caches). Deleting costs re-download time, nothing else.
- **CHECK** — probably fine, but verify one thing first: the owning app is
  running, the path is user-managed state, or cachekill simply doesn't know it.
  Unknown paths are CHECK, never SAFE.
- **SKIP** — user content (`Downloads`), system-managed dirs
  (`Library/Caches/com.apple.*`), and anything with hidden state
  (`~/.ollama/models` — grep your repos for model pins before `ollama rm`).

Deletion is **dry-run by default** and only ever applies to SAFE entries.
Running applications are detected with `pgrep` and their caches downgrade from
SAFE to CHECK ("quit the app first"). Sizes are du-style *allocated* bytes, so
sparse files (like Docker's `Docker.raw`: 24 GB apparent, ~1–7 GB allocated)
can't flatter the numbers.

Every rule in the registry earned its class the hard way, during a real
disk-reclaim session where 6.4 GB of cache clearing was almost fully offset by a
Docker VM image nobody had classified. The tool is that session, written down.

## Install

No dependencies, no install step — Python 3.10+ stdlib:

```bash
git clone https://github.com/Matthew-Selvam/cachekill
python3 cachekill/cachekill.py scan
```

macOS-first (`~/Library/Caches`, `~/Library/Containers`); the `~/.cache`,
`~/.npm`, `~/.bun`, `~/.gradle`, `~/.cargo` conventions work on Linux too.

## Usage

```bash
python3 cachekill.py scan                  # classify everything
python3 cachekill.py scan --min-mb 100     # hide the small stuff
python3 cachekill.py explain <path>        # why is this classified X?
python3 cachekill.py delete                # dry-run: what would SAFE deletion free?
python3 cachekill.py delete --apply        # actually delete SAFE entries
python3 cachekill.py delete --apply --path ~/.cache/puppeteer   # one entry
python3 cachekill.py scan --json           # machine-readable
```

Exit codes: `0` ok · `2` nothing matched · `3` a path you explicitly named was
refused by a safety rule (class not SAFE, symlink, single-segment path, or
`$HOME` itself).

`explain` is the escape hatch from the registry's opinions:

```
$ python3 cachekill.py explain ~/.cache/prek
path    /Users/you/.cache/prek
class   SAFE  (match: exact, 101.1 MB, 3239 files)
why     prek (pre-commit) hook virtualenvs
regen   prek re-creates envs on next run
```

## Design notes

- **Classify first, delete second.** The interesting output is the table, not
  the freed bytes. `delete` refuses anything that did not scan as SAFE.
- **Docker is a CHECK, never a target.** The space inside Docker lives in the
  VM image; you reclaim it with `docker builder prune --all` and
  `docker image prune -a` while the daemon runs — never by deleting `Docker.raw`
  from the outside. cachekill prints exactly that advice in its note.
- **`~/.ollama/models` is SKIP on purpose.** Model blobs look like cache but are
  config: which model your projects pin lives in their source, not on disk.
  Wrong move there silently breaks a vision connector (this happened).
- **Liveness-aware.** Browser caches are SAFE — after you quit the browser.
  If Chrome/Brave/Firefox/Spotify/bun/python is running, the entry downgrades
  to CHECK with that reason attached.
- **One file, stdlib only.** Auditable in a single sitting; nothing to install,
  nothing to break.

## Extending the registry

Add a `Rule(rel, cls, note, regen, app)` to `REGISTRY` in `cachekill.py`.
Rules are checked longest-prefix-first; `Library/Caches/com.apple.*` wildcards
match last. If your tool's cache is wrongly classified, a one-line PR with the
`explain` output before and after is the perfect issue.

## License

MIT
