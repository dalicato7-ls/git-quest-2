## Level 6 — Ship v1.0.0
*rebase · fast-forward · annotated tag · release*

Time to release. `main` must contain the login feature, with a **straight** history (no merge commit).

**1. Put the feature on top of the latest main, then fast-forward:**
```bash
git switch feature/login
git rebase main                    # main moved since level 4 (hotfix, security fix)
git push --force-with-lease        # the branch was rewritten, so a normal push is refused
git switch main
git merge --ff-only feature/login  # refuses if a merge commit would be needed
git log --oneline --graph -5       # one straight line
git push
```

**2. Tag the release** (annotated: it records who, when and why):
```bash
git tag -a v1.0.0 -m "v1.0.0: clean repo, hotfix, login, XSS fix"
git show v1.0.0
git push origin v1.0.0             # tags are not pushed by a plain git push
```

**3. Publish it:** your fork on GitHub → **Releases** → Draft a new release → choose tag `v1.0.0` → **Generate release notes** → Publish release.

Then **`/check`**.
