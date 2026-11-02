## Stage 4 — Collision Course
*conflict on a pull request · updating a branch*

Two members, **A** and **B**, start from the same `main`:
```bash
git switch main && git pull
git switch -c target-<login>
```
Both edit the **same line** of `mission.md`: `target: TBD` → `target: <your proposal>`. Commit, push, open a PR each.

1. Get **A**'s PR approved and merged.
2. **B**'s PR now says *This branch has conflicts that must be resolved*. **B** updates the branch:
```bash
git switch target-<B-login>
git pull origin main --no-rebase         # CONFLICT in mission.md
```
   Keep both proposals on one line, for example `target: lighthouse + harbor`, delete the markers, then:
```bash
git add mission.md
git commit --no-edit
git push
```
   (The PR's **Resolve conflicts** button does the same thing in the browser.)
3. Approve and merge **B**'s PR. Then **`/check`**.
