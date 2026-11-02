## Level 5 — Surgical Pick
*cherry-pick*

HQ's branch `release/experimental` has 3 commits. Two are experiments nobody approved. One is an urgent **security fix** for an XSS in `app/greet.js`. Bring **only** that one into your `main`.

```bash
git fetch upstream
git log --oneline main..upstream/release/experimental
git show <hash>                    # read each one: which is the security fix?
git switch main
git cherry-pick <hash-of-the-fix>
git log --oneline -3               # a new commit, same change, new hash
git push
```
Then **`/check`**.

> Don't `git merge upstream/release/experimental`: that would bring the experiments too.
