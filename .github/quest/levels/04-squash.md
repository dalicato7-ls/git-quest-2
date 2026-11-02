## Level 4 — Squash
*interactive rebase*

HQ's branch `messy/login` works, but its history is embarrassing: `wip`, `fix`, `fix again`... Before it goes anywhere near `main`, turn those 5 commits into **one** clean commit, placed on top of **your** `main`.

**1. Get HQ's branch:**
```bash
git remote add upstream https://github.com/{upstream}.git
git fetch upstream
git switch -c feature/login upstream/messy/login
git log --oneline main..feature/login     # the 5 messy commits
```

**2. Rewrite it:**
```bash
git rebase -i main
```
Your editor opens with a list, oldest first. Keep the first line as `pick` and change the 4 others to `squash` (or just `s`):
```text
pick   1a2b3c4 wip
squash 2b3c4d5 add login form
squash 3c4d5e6 fix
squash 4d5e6f7 fix again
squash 5e6f7a8 remove console.log
```
Save and close. A second editor asks for the message of the combined commit: delete everything and write exactly:
```text
feat: add login form
```
Save and close. Check:
```bash
git log --oneline main..feature/login     # exactly 1 commit
git push -u origin feature/login
```
Then **`/check`**.

> Lost? `git rebase --abort` puts everything back. Already pushed `feature/login` before rewriting it? Use `git push --force-with-lease`.
