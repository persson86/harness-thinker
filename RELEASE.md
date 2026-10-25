# Release recipe — harness-thinker

Follows `payload/harness/operations/release.md`. Machine-specific targets and extra clones live in `RELEASE.local.md` (git-ignored); this file stays generic because the repository is public.

- **Version:** `VERSION` only. The installer writes it to `harness/.version` in each target. Every release bumps the last number (`X.Y.Z` → `X.Y.(Z+1)`), a new skill included; minor and major only on explicit request; no pre-release suffixes. A legacy suffix is dropped instead (`7.23.0-rc.14` → `7.23.0`).
- **Tests:** `bash tests/run.sh` on the final tree (version and docs already bumped) must end with zero failures.
- **Docs:** a `## X.Y.Z - YYYY-MM-DD` entry at the top of `CHANGELOG.md`, stating what changed and what was not validated. A `## X.Y.Z: <title>` section in `README.md` after *Release discipline* when installation, usage, commands or visible behavior change; update the layout block when payload directories change. No personal data in any of them.
- **Commit:** reviewed paths only, message `feat: <summary> (X.Y.Z)` (or `fix:`/`docs:` as appropriate).
- **Tag:** `git tag -a vX.Y.Z -m "vX.Y.Z — <summary>"` on the release commit.
- **Remote:** `origin`, branch `main`. Push the branch, then the tag, by full refs and with `push.followTags=false`.
- **Reinstall:** for each target in `RELEASE.local.md`, `./install.sh <target> --update` from a tree identical to the tag: this clone when it has no pending changes, otherwise a clean `git worktree add <tmp> vX.Y.Z` (the installer reads the working tree). The installer refuses tracked collisions with generated skills; resolve them in the target, never by editing the installed copy.
- **Verify:** `<target>/harness/.version` equals `VERSION`; `bash <target>/harness/scripts/verify.sh` reports zero drift; `git ls-remote origin refs/heads/main 'refs/tags/vX.Y.Z^{}'` shows the release commit for both refs. Fast-forward the other clones listed in `RELEASE.local.md` when clean.
- **Rollback a target:** `git worktree add <tmp> v<previous>`, run `<tmp>/install.sh <target> --update`, verify, then `git worktree remove <tmp>`. The published release stays published; fixes ship as a new version.
