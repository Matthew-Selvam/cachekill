# Posting options, verified 2026-10-05

Every count measured programmatically. All under 280 raw chars. Zero stars,
so nothing claims traction.

The most interesting new fact is not the tool, it is what it refused to delete.

---

## 1. The disk story (270) <- best first post, already drafted

Disk hit 99%. Cleared 6.4 GB of caches, and free space went DOWN. Docker's VM image ate every byte back in the background. So I built cachekill: classifies every cache SAFE / CHECK / SKIP before you delete. Dry-run by default. https://github.com/Matthew-Selvam/cachekill

## 2. The 20 GB I did not delete (277) <- strongest if you want a standout

Found 20 GB hiding in my own Mac: a 10 GB Claude VM image, plus a second near-copy under Application Support/Chromium, both from August. Same 10 GB base, different state written on top. My cache tool refused to touch them, correctly. https://github.com/Matthew-Selvam/cachekill

## 3. The sparse-file gotcha (261)

Docker.raw says 24 GB. It was allocating 979 MB. Tools that report apparent size will gaslight you. cachekill measures allocated bytes and classifies every cache SAFE / CHECK / SKIP before deleting. Python, zero deps. https://github.com/Matthew-Selvam/cachekill

## 4. The honest postmortem (258) <- pairs well with 1, post after it

A review of my cache tool found 3 real bugs: depth-3 caches never scanned, --json documented wrong, a python liveness check that matched itself. All fixed and retested. "Verified end to end" is a claim, not a fact. https://github.com/Matthew-Selvam/cachekill

## 5. The design stance (257)

My disk-reclaim tool only deletes caches it can prove are regenerable. Everything else is CHECK or SKIP with the reason printed. It found 3.6 GB safe on my Mac and refused the rest. Dry-run by default, no --force. https://github.com/Matthew-Selvam/cachekill

---

## Correction worth knowing before you post option 2

I originally described the two VM images as identical duplicates. They are not.
Verified by comparison: identical for the first 50 MB, then 17 of 32 sampled
1 MB windows differ across the middle, and the tails differ too. Same 10 GB base
image, different VM state written on top. Both are ~9.9 to 10 GB *allocated*
(not sparse), from Aug 14, with no Claude or Chromium process running.

So: ~20 GB of app state, not cache. cachekill correctly refused it (Application
Support is out of scope by design). Deleting the Chromium one frees ~9.9 GB;
deleting both frees ~20 GB with a re-download on next launch. Still awaiting
your go-ahead.

## Fact ledger

- "20 GB / 10 GB Claude VM image / second near-copy under Chromium": measured,
  10737418240 bytes apparent each, 10.00 GB and 9.93 GB allocated.
- "both from August": mtime Aug 14 2026 on both bundles.
- "My cache tool refused to touch them, correctly": cachekill scans
  Library/Caches and other cache roots only; Application Support has no rule and
  no scan root.
- "3.6 GB safe on my Mac": live `cachekill scan --min-mb 50` SAFE total, this
  session.
- Review-bug claims (option 4): D1 depth-3 scan, D3 --json placement, D2 python
  self-match, all fixed in commit 455ccdf.
- Docker.raw 24 GB apparent / 979 MB allocated: measured pre-existing state.
