#!/usr/bin/env python3
"""cachekill: see what is safe to delete on a full disk before you delete it.

Every path is classified before anything is touched:

  SAFE   pure regenerable cache. Deleting costs re-download time, nothing else.
  CHECK  probably fine, but verify one thing first (app running, models pinned...).
  SKIP   user content, managed app state, or anything cachekill cannot classify.

cachekill is conservative by design: unknown paths are SKIP, delete is dry-run
by default, and running applications downgrade their caches to CHECK.

Stdlib only. macOS-first (~/Library/Caches, ~/Library/Containers), but the
~/.cache, ~/.npm, ~/.bun, ~/go conventions work on Linux too.

Usage:
  python3 cachekill.py scan [--min-mb N] [--json]
  python3 cachekill.py explain <path>
  python3 cachekill.py delete [--apply] [--min-mb N] [--path P ...] [--json]

Exit codes: 0 ok · 2 nothing matched · 3 a path was refused by a safety rule.
"""

from __future__ import annotations

import argparse
import json as _json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass

HOME = os.path.expanduser("~")

SAFE = "SAFE"
CHECK = "CHECK"
SKIP = "SKIP"

# ---------------------------------------------------------------------------
# Registry: each entry earned its class the hard way (a real disk-reclaim
# session). `app` is an optional process-name fragment: when that process is
# running, a SAFE cache is downgraded to CHECK ("quit the app first").
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    rel: str  # path relative to $HOME, no trailing slash
    cls: str
    note: str
    regen: str = ""  # how the cache comes back
    app: str = ""  # pgrep fragment; empty = no liveness check


REGISTRY: tuple[Rule, ...] = (
    Rule(".bun/install/cache", SAFE, "bun package tarball cache",
         "bun install re-downloads on demand"),
    Rule(".npm/_cacache", SAFE, "npm content-addressed cache",
         "npm cache verify / next install"),
    Rule(".npm/_logs", SAFE, "npm debug logs", "next npm run"),
    Rule(".cache/uv", SAFE, "uv wheel + index cache", "next uv sync/pip"),
    Rule("Library/Caches/pip", SAFE, "pip download cache", "next pip install"),
    Rule("Library/Caches/bun", SAFE, "bun toolchain cache", "next bun run",
         app="bun"),
    Rule("go/pkg/mod", CHECK,
         "Go module cache. Clean with `go clean -modcache`, not by rm",
         "go mod download"),
    Rule(".cache/puppeteer", SAFE, "puppeteer Chromium builds",
         "next puppeteer install re-downloads"),
    Rule("Library/Caches/ms-playwright", SAFE, "playwright browser binaries",
         "npx playwright install"),
    Rule(".cache/huggingface", SAFE, "HF hub models, re-download on demand",
         "transformers snapshot_download"),
    Rule(".cache/torch", SAFE, "torch hub checkpoints", "on demand"),
    Rule(".cache/chroma/onnx_models", SAFE, "chroma default embedder model",
         "chroma re-downloads on first use"),
    Rule(".cache/mongodb-binaries", SAFE, "mongodb runner binaries",
         "mongodb-memory-server re-downloads"),
    Rule(".cache/ms-playwright", SAFE, "playwright browser binaries (Linux path)",
         "npx playwright install"),
    Rule(".cache/prek", SAFE, "prek (pre-commit) hook virtualenvs",
         "prek re-creates envs on next run"),
    Rule(".cache/node", SAFE, "corepack shims/keys cache", "corepack re-fetches"),
    Rule(".cache/typescript", SAFE, "tsc incremental buildinfo",
         "next tsc build"),
    Rule(".gradle/caches", SAFE, "gradle dependency + build cache",
         "next gradle build"),
    Rule(".cargo/registry/cache", SAFE, "crates.io tarball cache",
         "cargo fetch"),
    Rule(".cargo/registry/src", SAFE, "extracted crate sources", "cargo fetch"),
    Rule(".cargo/registry/index", SAFE, "crates.io index clone",
         "cargo fetch re-clones"),
    Rule("Library/Caches/com.spotify.client", SAFE, "Spotify audio/HTTP cache",
         "Spotify rebuilds it", app="Spotify"),
    Rule("Library/Caches/BraveSoftware", SAFE, "Brave browser HTTP cache",
         "Brave rebuilds it", app="Brave Browser"),
    Rule("Library/Caches/Google/Chrome", SAFE, "Chrome HTTP cache",
         "Chrome rebuilds it", app="Chrome"),
    Rule("Library/Caches/Firefox", SAFE, "Firefox HTTP cache",
         "Firefox rebuilds it", app="firefox"),
    Rule("Library/Caches/GeoServices", SKIP, "Apple Maps tiles; macOS owns it"),
    Rule(".npm/_npx", CHECK, "npx-installed packages; regenerable but re-fetches on next npx",
         "next npx <pkg>"),
    # --- Apple system-managed: never touch ---
    Rule("Library/Caches/com.apple.*", SKIP, "system-managed; macOS owns it"),
    Rule("Library/Caches/CloudKit", SKIP, "system-managed; macOS owns it"),
    Rule("Library/Caches/com.apple.helpd", SKIP, "system-managed; macOS owns it"),
    # --- Deliberate skip: state or user content, not cache ---
    Rule(".ollama/models", SKIP,
         "local LLM blobs. Grep your repos for model pins before `ollama rm`"),
    Rule("Library/Containers/com.docker.docker", CHECK,
         "Docker VM disk image. Reclaim INSIDE docker (builder/image prune), "
         "never by deleting Docker.raw"),
    Rule("Downloads", SKIP, "user content"),
    Rule(".rustup", CHECK, "rustup toolchains. Deleting breaks offline builds",
         "rustup toolchain install"),
    Rule("ComfyUI-Installs", SKIP, "user content"),
    Rule(".claude", SKIP, "agent state + managed plugin checkouts"),
    Rule(".openclaude", SKIP, "agent state + managed plugin checkouts"),
    Rule(".hermes", SKIP, "active agent session state"),
    Rule("node_modules", CHECK,
         "project dependencies. Deleting is safe but breaks running dev servers",
         "package manager install"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rel(path: str) -> str:
    p = os.path.abspath(os.path.expanduser(path))
    if p == HOME:
        return ""
    home_prefix = HOME.rstrip("/") + "/"
    if p.startswith(home_prefix):
        return p[len(home_prefix):]
    return p.lstrip("/")


def _rule_for(rel: str) -> tuple[Rule | None, str]:
    """Return (matching rule, match kind). Longest prefix wins; * patterns last."""
    best: Rule | None = None
    kind = ""
    best_len = -1
    for r in REGISTRY:
        if r.rel.endswith(".*"):
            base = r.rel[:-2]
            if rel == base or rel.startswith(base + "/"):
                if best_len < 0:  # wildcard: lowest priority
                    best, kind, best_len = r, "wildcard", 0
            continue
        if rel == r.rel:
            if best_len < len(r.rel):
                best, kind, best_len = r, "exact", len(r.rel)
        elif rel.startswith(r.rel + "/"):
            if best_len < len(r.rel):
                best, kind, best_len = r, "child-of", len(r.rel)
    return best, kind


def _app_running(fragment: str) -> bool:
    """True when a process matching `fragment` is running, other than us.

    `pgrep -f` matches our own interpreter (any `app="python"` rule would
    permanently self-downgrade, because cachekill runs under python), so our
    own PID and its ancestors are excluded before the match.
    """
    if not fragment:
        return False
    try:
        r = subprocess.run(
            ["pgrep", "-if", fragment],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        return False
    matched = {int(x) for x in r.stdout.split() if x.strip().isdigit()}
    if not matched:
        return False
    # Exclude ourselves and our ancestors: pgrep skips its own process but not
    # the interpreter or shell that launched us, so an app fragment like
    # "python" or "bun" could otherwise match cachekill's own process tree.
    excluded = set()
    pid = os.getpid()
    for _ in range(15):
        if pid in excluded or pid <= 1:
            break
        try:
            out = subprocess.run(
                ["ps", "-o", "ppid=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            ppid = int(out.split()[0])
        except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
            break
        excluded.add(pid)
        excluded.add(ppid)
        pid = ppid
    return bool(matched - excluded)


def classify(path: str) -> tuple[str, str, str, str]:
    """Return (class, note, regen, match_kind) for an absolute path."""
    rel = _rel(path)
    if not rel:  # home itself
        return SKIP, "this is $HOME, refusing by definition", "", "home"
    rule, kind = _rule_for(rel)
    if rule is None:
        return (CHECK, "unknown to cachekill, verify by hand", "", "unknown")
    cls, note, regen = rule.cls, rule.note, rule.regen
    if rule.app and cls == SAFE and _app_running(rule.app):
        cls = CHECK
        note += f", '{rule.app}' is running; quit it first"
    return cls, note, regen, kind


def tree_size(path: str) -> tuple[int, int]:
    """(bytes, files) under path, without following symlinks. Best effort."""
    total = 0
    files = 0
    for root, dirs, names in os.walk(path, followlinks=False):
        for d in dirs:
            p = os.path.join(root, d)
            if os.path.islink(p):
                dirs.remove(d)
        for n in names:
            p = os.path.join(root, n)
            if os.path.islink(p):
                continue
            try:
                st = os.lstat(p)
                total += st.st_blocks * 512  # allocated, du-style; honest for sparse files
                files += 1
            except OSError:
                pass
    return total, files


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024.0
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

SCAN_ROOTS = (
    ".cache",
    ".npm",
    ".bun/install",
    "Library/Caches",
    "go/pkg/mod",
    ".gradle/caches",
    ".cargo/registry",
    "Library/Containers/com.docker.docker/Data/vms",
)


def scan(min_mb: int = 0, roots: tuple[str, ...] = SCAN_ROOTS) -> list[dict]:
    """Classify cache dirs under each root, two levels deep.

    Depth 1 entries are always considered (including unknowns, which classify
    as CHECK). Depth 2 entries are considered only when a registry rule names
    them, so unrelated subdirs do not flood the output. Nodes that are mere
    prefixes of a deeper canonical rule (e.g. `.cache/chroma` when the rule
    targets `.cache/chroma/onnx_models`) are skipped in favor of the deeper
    node, and a node whose rule ancestor was already emitted is skipped too,
    so nothing is ever double-counted in the totals.
    """
    entries: list[dict] = []
    seen: set[str] = set()

    def consider(path: str, allow_unknown: bool) -> None:
        if path in seen or not os.path.isdir(path):
            return
        if os.path.dirname(path) in seen:
            # an emitted ancestor already counted this subtree
            return
        rel = _rel(path)
        rule, kind = _rule_for(rel)
        if rule is None:
            if not allow_unknown:
                return
            if any(r.rel.startswith(rel + "/") for r in REGISTRY):
                # a known rule lives deeper; its node will represent this subtree
                return
        elif kind != "wildcard" and rule.rel != rel and rule.rel.startswith(rel + "/"):
            # canonical rule node is deeper (e.g. .../Google -> .../Google/Chrome);
            # defer so the entry carries the canonical path
            return
        seen.add(path)
        cls, note, regen, kind = classify(path)
        size, nfiles = tree_size(path)
        if size < min_mb * 1024 * 1024:
            return
        entries.append({
            "path": path,
            "class": cls,
            "size_bytes": size,
            "size": human(size),
            "files": nfiles,
            "note": note,
            "regen": regen,
            "match": kind,
        })

    for rel_root in roots:
        root = os.path.join(HOME, rel_root)
        if not os.path.isdir(root):
            continue
        # a root that is itself a registry rule is an entry in its own right;
        # the parent-seen guard then keeps its children from double-counting
        if _rule_for(rel_root)[0] is not None and _rule_for(rel_root)[1] == "exact":
            consider(root, allow_unknown=True)
        try:
            children = sorted(os.listdir(root))
        except OSError:
            continue
        for child in children:
            path = os.path.join(root, child)
            consider(path, allow_unknown=True)
            try:
                grandchildren = sorted(os.listdir(path))
            except OSError:
                continue
            for gc in grandchildren:
                consider(os.path.join(path, gc), allow_unknown=False)
    entries.sort(key=lambda e: -e["size_bytes"])
    return entries


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def _refusal(path: str, cls: str) -> str | None:
    p = os.path.abspath(os.path.expanduser(path))
    if p == HOME or p == "/":
        return "refusing: path is home or root"
    parts = _rel(p).split("/")
    if len(parts) < 2 and not p.startswith(os.path.join(HOME, "Library")):
        return "refusing: top-level single-segment path"
    if cls != SAFE:
        return f"refusing: class is {cls} (only SAFE is deletable)"
    if os.path.islink(p):
        return "refusing: path itself is a symlink"
    return None


def delete_plan(entries: list[dict], apply: bool) -> tuple[list[dict], int]:
    planned, freed = [], 0
    for e in entries:
        why = _refusal(e["path"], e["class"])
        if why:
            e = dict(e, action="refused", why=why)
        elif apply:
            shutil.rmtree(e["path"], ignore_errors=False)
            e = dict(e, action="deleted", why="")
            freed += e["size_bytes"]
        else:
            e = dict(e, action="would-delete", why="")
            freed += e["size_bytes"]
        planned.append(e)
    return planned, freed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_table(entries: list[dict]) -> None:
    if not entries:
        print("nothing matched")
        return
    w = max(len(e["path"]) for e in entries)
    w = min(w, 70)
    print(f"{'SIZE':>10}  {'CLASS':<5}  {'PATH':<{w}}  NOTE")
    for e in entries:
        p = e["path"]
        if len(p) > w:
            p = "…" + p[-(w - 1):]
        print(f"{e['size']:>10}  {e['class']:<5}  {p:<{w}}  {e['note'][:60]}")
    totals: dict[str, int] = {}
    for e in entries:
        totals[e["class"]] = totals.get(e["class"], 0) + e["size_bytes"]
    print("")
    for cls in (SAFE, CHECK, SKIP):
        if cls in totals:
            print(f"  {cls:<5} total: {human(totals[cls])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cachekill", description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def _add_json(p):
        # accept --json on either side of the subcommand; the module docstring
        # and README document the post-subcommand form
        p.add_argument("--json", dest="sub_json", action="store_true",
                       help=argparse.SUPPRESS)

    sp = sub.add_parser("scan", help="classify cache dirs")
    sp.add_argument("--min-mb", type=int, default=0)
    _add_json(sp)

    ep = sub.add_parser("explain", help="why is this path classified X")
    ep.add_argument("path")
    _add_json(ep)

    dp = sub.add_parser("delete", help="dry-run (default) or --apply delete of SAFE entries")
    dp.add_argument("--apply", action="store_true")
    dp.add_argument("--min-mb", type=int, default=0)
    dp.add_argument("--path", action="append", default=[],
                    help="restrict to these paths (repeatable)")
    _add_json(dp)

    args = ap.parse_args(argv)
    args.json = args.json or getattr(args, "sub_json", False)

    if args.cmd == "explain":
        p = os.path.abspath(os.path.expanduser(args.path))
        if not os.path.exists(p):
            print(f"no such path: {p}", file=sys.stderr)
            return 2
        cls, note, regen, kind = classify(p)
        size, nfiles = tree_size(p)
        info = {
            "path": p, "class": cls, "note": note, "regen": regen,
            "match": kind, "size": human(size), "files": nfiles,
        }
        if args.json:
            print(_json.dumps(info, indent=2))
        else:
            print(f"path    {info['path']}")
            print(f"class   {cls}  (match: {kind}, {info['size']}, {nfiles} files)")
            print(f"why     {note}")
            if regen:
                print(f"regen   {regen}")
        return 0

    if args.cmd == "scan":
        entries = scan(min_mb=args.min_mb)
        if args.json:
            print(_json.dumps(entries, indent=2))
        else:
            _print_table(entries)
        return 0 if entries else 2

    if args.cmd == "delete":
        entries = scan(min_mb=args.min_mb)
        explicit = bool(args.path)
        if explicit:
            want = {os.path.abspath(os.path.expanduser(p)) for p in args.path}
            entries = [e for e in entries if e["path"] in want]
            if not entries:
                print("no scanned entry matches --path", file=sys.stderr)
                return 2
        else:
            # bare delete: the plan is exactly the SAFE set
            entries = [e for e in entries if e["class"] == SAFE]
            if not entries:
                print("no SAFE entries to delete", file=sys.stderr)
                return 2
        planned, freed = delete_plan(entries, apply=args.apply)
        if args.json:
            print(_json.dumps({"planned": planned, "freed": human(freed),
                               "freed_bytes": freed}, indent=2))
        else:
            _print_table(planned)
            verb = "deleted" if args.apply else "would delete"
            print(f"\n  {verb}: {human(freed)}")
            for e in planned:
                if e.get("action") == "refused":
                    print(f"  refused: {e['path']} : {e['why']}")
        return 3 if any(e.get("action") == "refused" for e in planned) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
