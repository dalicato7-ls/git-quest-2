## Level 1 — Clean Room
*.gitignore · git rm --cached*

Clone **your fork** and look at what a real project folder looks like after a day of work:
```bash
git clone https://github.com/{fork}.git
cd {repo}
cp .env.example .env               # your local secrets (fake ones)
echo "boot ok" > debug.log         # a log your app wrote
mkdir -p build && echo bin > build/app.bin   # a build output
git status                         # junk everywhere, and server.log is even committed!
```

**Mission:** create a `.gitignore` at the root so that Git ignores:
- `.env` (but **not** `.env.example`: teammates need the template)
- every `*.log` file, in any folder
- the `build/` folder
- every `__pycache__/` folder

Test your rules before committing:
```bash
git check-ignore -v .env debug.log build/app.bin   # each one should print the rule that matches
git check-ignore -v .env.example                   # should print nothing
```

`server.log` was committed by an intern. `.gitignore` never untracks a file Git already follows, so remove it from Git **without deleting your copy**:
```bash
git rm --cached server.log
git status                         # new file: .gitignore · deleted: server.log
git add .gitignore
git commit -m "chore: ignore local and generated files"
git push
```
Then **`/check`**.
