## Level 2 — Keymaster
*SSH keys · signed commits*

Anyone can write `git config user.email torvalds@linux-foundation.org` and commit "as Linus". A **signature** proves a commit really comes from you. We'll use one SSH key for both: logging in to GitHub and signing commits. Needs Git 2.34 or newer (`git --version`).

**1. Create a key pair** (press Enter to accept the default path; a passphrase is recommended):
```bash
ssh-keygen -t ed25519 -C "you@example.com"
cat ~/.ssh/id_ed25519.pub          # the PUBLIC key: this is the one you share
```
Never share `~/.ssh/id_ed25519` (no `.pub`): that's your private key.

**2. Give the public key to GitHub, twice:** github.com → Settings → **SSH and GPG keys** → New SSH key
- Title: `laptop`, Key type: **Authentication Key**, paste → Add
- New SSH key again, Key type: **Signing Key**, paste the same line → Add

**3. Log in with SSH and switch your clone to it:**
```bash
ssh -T git@github.com              # "Hi {login}! You've successfully authenticated"
git remote set-url origin git@github.com:{fork}.git
git remote -v
```
Port 22 blocked on this network? Use `ssh -T -p 443 git@ssh.github.com` and see the hint in the slides.

**4. Sign every commit from now on:**
```bash
git config --global gpg.format ssh
git config --global user.signingkey ~/.ssh/id_ed25519.pub
git config --global commit.gpgsign true
git config --global user.email     # must be an email verified on your GitHub account
```

**5. Make a signed commit and push it:**
```bash
printf "agent: {login}\nsigned: yes\n" > agents/{login}.md
git add agents/{login}.md
git commit -m "feat: signed agent card"
git push
```
Open the commit on GitHub: it should show a green **Verified** badge. Then **`/check`**.
