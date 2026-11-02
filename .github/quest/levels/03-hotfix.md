## Level 3 — Hotfix
*stash · switch*

You're in the middle of a feature when production breaks. Your work isn't ready to commit. That's what `git stash` is for.

**1. Start the feature:**
```bash
git switch -c feature/dark-mode
```
In `app/config.txt`, change `theme: light` to `theme: dark`, then:
```bash
git commit -am "feat: dark theme"
```
Keep working: add a new line `accent: purple` to `app/config.txt`. **Don't commit it.**

**2. Alert: production is down.** `timeout: 0` on `main` makes every request fail. Try to go fix it:
```bash
git switch main                    # refused: your local changes would be overwritten
git stash                          # put your unfinished work on a shelf
git stash list                     # stash@{0}: WIP on feature/dark-mode
git switch main
```
In `app/config.txt` set `timeout: 30`, then:
```bash
git commit -am "fix: restore request timeout"
git push
```

**3. Back to your feature:**
```bash
git switch feature/dark-mode
git stash pop                      # your accent line is back
git commit -am "feat: purple accent"
git push -u origin feature/dark-mode
```
Then **`/check`**.
