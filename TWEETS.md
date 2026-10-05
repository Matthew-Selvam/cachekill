# cachekill: tweet options (verified 2026-10-05)

All four measure <=280 raw characters. Counts re-measured programmatically
after the dash-free rewrite (see per-option numbers below). Raw-char is the
strictest measure (weighted counts only help you).

Pick one and paste. Angles are materially different, not paraphrases.

---

## A: the story (270) <- recommended; the anecdote is documented, not invented

Disk hit 99%. Cleared 6.4 GB of caches, and free space went DOWN. Docker's VM image ate every byte back in the background. So I built cachekill: classifies every cache SAFE / CHECK / SKIP before you delete. Dry-run by default. https://github.com/Matthew-Selvam/cachekill

## B: the pitch (275)

cachekill sorts your caches before you rm them: SAFE (regenerable), CHECK (owning app is running, quit it first), SKIP (user content, app state). Dry-run by default, refuses anything not verifiably regenerable. One file, zero deps. https://github.com/Matthew-Selvam/cachekill

## C: the sparse-file gotcha (270)

Docker.raw said 24 GB. It was allocating 1 GB. Disk tools reporting apparent size will gaslight you all day. cachekill measures allocated bytes and classifies every cache SAFE / CHECK / SKIP before deletion. Python, zero deps. https://github.com/Matthew-Selvam/cachekill

## D: the fear (276)

The scariest moment in dev: disk at 99% and you're about to rm -rf something you're not sure about. cachekill classifies every cache on your Mac SAFE / CHECK / SKIP first, and won't delete anything that isn't verifiably regenerable. https://github.com/Matthew-Selvam/cachekill

---

## Fact ledger (every claim above, checked against source)

- "Disk hit 99% / cleared 6.4 GB / free space went DOWN": from the
  2026-10-01 disk-reclaim handoff doc: 99% full, ~6.4 GB cleared,
  free dropped 317 MB in the same window. Documented, first-party.
- "Docker's VM image ate every byte back": same handoff, Docker.raw grew
  ~6.7 GB during the session vs 6.4 GB reclaimed.
- "SAFE / CHECK / SKIP": the three classes in cachekill.py REGISTRY.
- "Dry-run by default": `delete` without `--apply` never touches disk.
- "Refuses anything not verifiably regenerable": `_refusal()` deletes only
  SAFE-classified paths; CHECK/SKIP are refused with exit code 3 (tested).
- "One file, zero deps": cachekill.py, stdlib imports only; verified.
- "Docker.raw said 24 GB / allocating 1 GB": apparent 24 GB, allocated 979 MB
  as measured 2026-10-05 post-prune (7.0 GB pre-prune). Numbers measured, not
  remembered.
- "Every cache on your Mac": every scanned dir gets a class; unknowns surface
  as CHECK ("unknown to cachekill, verify by hand"), so nothing is silently
  unclassified.

## Caveats

- Repo is 4 commits, zero stars, published today. Nothing in the tweets claims
  adoption, so nothing can contradict that.
- If Matthew posts under a personal account, A reads as personal ("I built"),
  which is intentional. B/C/D are product-voice and fine from any account.
- Star count / "as of today" framing deliberately omitted; those go stale.
