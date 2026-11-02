"""
Git Quest season 2 — solo level checks.

Every check receives a Ctx and returns Result(ok, reason, hint).
Forks are inspected through a *bare* clone: nothing from a student's
repository is checked out or executed — only git objects are read.
"""
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

WEB_EMAIL = "noreply@github.com"          # committer of every commit made on github.com
MARKER_RE = r"^(<<<<<<<|>>>>>>>)( |$)|^=======$"
SSH_SIG = "-----BEGIN SSH SIGNATURE-----"


@dataclass
class Result:
    ok: bool
    reason: str = ""
    hint: str = ""
    data: dict = field(default_factory=dict)


def ok(**data):
    return Result(True, data=data)


def fail(reason, hint=""):
    return Result(False, reason, hint)


class Git:
    def __init__(self, git_dir):
        self.git_dir = git_dir

    def run(self, *args, check=True, stdin=None):
        p = subprocess.run(["git", "--git-dir", self.git_dir, *args], input=stdin,
                           capture_output=True, text=True, timeout=60)
        if check and p.returncode != 0:
            raise RuntimeError(p.stderr.strip())
        return p

    def out(self, *args):
        p = self.run(*args, check=False)
        return p.stdout if p.returncode == 0 else None

    def rev(self, ref):
        o = self.out("rev-parse", "--verify", "--quiet", ref + "^{commit}")
        return o.strip() if o else None

    def show(self, ref, path):
        return self.out("show", f"{ref}:{path}")

    def blob(self, ref, path):
        o = self.out("rev-parse", "--verify", "--quiet", f"{ref}:{path}")
        return o.strip() if o else None

    def is_ancestor(self, a, b):
        return self.run("merge-base", "--is-ancestor", a, b, check=False).returncode == 0

    def subject(self, sha):
        return (self.out("log", "-1", "--format=%s", sha) or "").strip()

    def parents(self, sha):
        return (self.out("log", "-1", "--format=%P", sha) or "").split()

    def committer_email(self, sha):
        return (self.out("log", "-1", "--format=%ce", sha) or "").strip()

    def raw(self, sha):
        return self.out("cat-file", "commit", sha) or ""

    def files_of(self, sha):
        o = self.out("diff-tree", "--no-commit-id", "--name-only", "-r", sha) or ""
        return sorted(l for l in o.splitlines() if l)

    def names_between(self, a, b):
        o = self.out("diff", "--name-only", a, b) or ""
        return sorted(l for l in o.splitlines() if l)

    def rev_list(self, *args):
        return (self.out("rev-list", *args) or "").split()

    def all_commits(self):
        return set(self.rev_list("--all"))

    def patch_id(self, sha):
        show = self.run("show", "--format=", "--no-color", sha, check=False).stdout
        p = subprocess.run(["git", "patch-id", "--stable"], input=show, capture_output=True, text=True)
        return p.stdout.split()[0] if p.stdout.strip() else None


def parse_fields(text):
    fields = {}
    for line in (text or "").splitlines():
        m = re.match(r"^\s*[-*]?\s*([A-Za-z_]+)\s*:\s*(.*?)\s*$", line)
        if m and not line.strip().startswith(("#", "<!--")):
            fields.setdefault(m.group(1).lower(), m.group(2).strip("`*_ "))
    return fields


class Ctx:
    """Everything a check needs to know about one student."""

    def __init__(self, login, fork, fork_git, upstream_git, upstream_ref, config, api=None,
                 upstream_repo="", up_prefix="origin/"):
        self.login = login
        self.fork = fork
        self.g = Git(fork_git)
        self.up = Git(upstream_git)
        self.up_ref = upstream_ref
        self.up_prefix = up_prefix          # how HQ branches are named in the upstream checkout
        self.cfg = config
        self.api = api
        self.upstream_repo = upstream_repo
        self.main = config.get("default_branch", "main")
        self._up_all = None

    def up_branch(self, name):
        return self.up.rev(self.up_prefix + name) or self.up.rev(name)

    def upstream_commits(self):
        if self._up_all is None:
            self._up_all = self.up.all_commits()
        return self._up_all

    def own_commits(self, ref):
        """Commits reachable from ref that HQ doesn't have, newest first, merges excluded."""
        ups = self.upstream_commits()
        return [s for s in self.g.rev_list("--no-merges", ref) if s not in ups]


# ---------------------------------------------------------------------------
# Level 1 — Clean Room
# ---------------------------------------------------------------------------
MUST_IGNORE = [".env", "debug.log", "logs/app.log", "build/app.bin", "__pycache__/cache.pyc", "app/__pycache__/x.pyc"]
MUST_KEEP = [".env.example", ".gitignore", "app/config.txt", "app/greet.js"]


def ignored_set(gitignore_text, paths):
    """Which paths does this .gitignore ignore? Uses git's own matcher (check-ignore --no-index)."""
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True, capture_output=True)
        rules = os.path.join(d, "rules")
        with open(rules, "w", encoding="utf-8") as f:
            f.write(gitignore_text)
        res = set()
        for p in paths:
            r = subprocess.run(["git", "-C", d, "-c", f"core.excludesFile={rules}", "check-ignore", "-q", "--no-index", p],
                               capture_output=True)
            if r.returncode == 0:
                res.add(p)
        return res


def check_clean(c: Ctx):
    gi = c.g.show(c.main, ".gitignore")
    if gi is None:
        return fail(f"There's no `.gitignore` at the root of `{c.main}` on your fork.",
                    "Create `.gitignore` next to README.md, commit it, push.")
    ign = ignored_set(gi, MUST_IGNORE + MUST_KEEP)
    missing = [p for p in MUST_IGNORE if p not in ign]
    if missing:
        return fail("Your `.gitignore` doesn't ignore: " + ", ".join(f"`{p}`" for p in missing) + ".",
                    "Test it locally with `git check-ignore -v <path>`. Patterns to know: `*.log`, `build/`, `__pycache__/`, `.env`.")
    wrongly = [p for p in MUST_KEEP if p in ign]
    if wrongly:
        return fail("Your `.gitignore` also ignores files that must stay tracked: " + ", ".join(f"`{p}`" for p in wrongly) + ".",
                    "`.env*` catches `.env.example` too. Either write `.env` alone, or add `!.env.example` on the next line.")
    if c.g.blob(c.main, ".env"):
        return fail("`.env` is committed on `main`. That's exactly the file that must never be pushed.",
                    "`git rm --cached .env` → commit → push. Then treat those values as leaked.")
    if c.g.blob(c.main, "server.log"):
        return fail("`server.log` is still tracked. `.gitignore` never untracks a file Git already follows.",
                    "`git rm --cached server.log` (keeps your local copy) → commit → push.")
    if not c.g.blob(c.main, ".env.example"):
        return fail("`.env.example` disappeared from `main`. It's the template teammates need: keep it tracked.",
                    "`git restore --source=HEAD~1 .env.example` (or from an older commit), commit, push.")
    return ok()


# ---------------------------------------------------------------------------
# Level 2 — Keymaster
# ---------------------------------------------------------------------------
REASON_HINTS = {
    "unknown_key": "GitHub doesn't know that key **as a signing key**. Settings → SSH and GPG keys → New SSH key → Key type: **Signing Key**, paste the same `.pub`.",
    "not_signing_key": "That key is registered for authentication only. Add it again with Key type: **Signing Key**.",
    "no_user": "The commit's email isn't one of your GitHub emails. `git config --global user.email` must match an email in Settings → Emails.",
    "unverified_email": "The commit's email isn't verified on GitHub. Verify it in Settings → Emails, or use your `@users.noreply.github.com` address.",
    "bad_email": "The commit's email isn't one of your GitHub emails. Fix `git config --global user.email`, then make a new signed commit.",
    "unsigned": "GitHub sees no signature. Check `git config --global commit.gpgsign` is `true` and `gpg.format` is `ssh`.",
    "invalid": "The signature doesn't match the commit. Make a fresh signed commit.",
    "malformed_signature": "The signature is malformed. Check `user.signingkey` points to your `.pub` file.",
}


def check_keymaster(c: Ctx):
    mine = c.own_commits("--all")[:40]
    if not mine:
        return fail("I don't see any commit of yours yet.", "Finish Level 1 first.")
    ssh_signed = [s for s in mine if SSH_SIG in c.g.raw(s) and c.g.committer_email(s) != WEB_EMAIL]
    gpg_signed = [s for s in mine if "-----BEGIN PGP SIGNATURE-----" in c.g.raw(s) and c.g.committer_email(s) != WEB_EMAIL]
    if not ssh_signed:
        if gpg_signed:
            return fail("I found a GPG-signed commit, but this level is about **SSH** signing.",
                        "`git config --global gpg.format ssh` and `git config --global user.signingkey ~/.ssh/id_ed25519.pub`, then commit again.")
        return fail("None of your pushed commits carries an SSH signature.",
                    "Set `gpg.format ssh`, `user.signingkey`, `commit.gpgsign true` (see the mission), make a new commit, push it.")
    if c.api is None:
        return ok(sha=ssh_signed[0])
    last_reason = None
    for sha in ssh_signed[:5]:
        info = c.api.commit(c.fork, sha)
        ver = ((info or {}).get("commit") or {}).get("verification") or {}
        if ver.get("verified"):
            return ok(sha=sha)
        last_reason = ver.get("reason") or "unknown"
    return fail(f"Your commit is SSH-signed, but GitHub says **Unverified** (`{last_reason}`).",
                REASON_HINTS.get(last_reason, "Open the commit on GitHub and click the Unverified badge: it says why."))


# ---------------------------------------------------------------------------
# Level 3 — Hotfix (stash)
# ---------------------------------------------------------------------------
def check_hotfix(c: Ctx):
    m = parse_fields(c.g.show(c.main, "app/config.txt"))
    br = "feature/dark-mode"
    tip = c.g.rev(br)
    if m.get("timeout") != "30":
        return fail(f"On `{c.main}`, `app/config.txt` still says `timeout: {m.get('timeout', '?')}`. Production is still down.",
                    f"Stash your work, `git switch {c.main}`, set `timeout: 30`, commit, push.")
    if "accent" in m:
        return fail(f"Your unfinished `accent:` line ended up on `{c.main}`. That's exactly what stash prevents.",
                    f"On `{c.main}`, delete the `accent:` line, commit, push. Next time: `git stash` before switching.")
    if m.get("theme") != "light":
        return fail(f"`{c.main}` has `theme: {m.get('theme')}`: the dark-mode feature leaked into main.",
                    f"On `{c.main}`, put back `theme: light`, commit, push. The feature stays on its branch.")
    if not any("app/config.txt" in c.g.files_of(s) for s in c.own_commits(c.main)):
        return fail("I can't find your hotfix commit on `main`.", "Commit the `timeout: 30` fix on main and push it.")
    if not tip:
        return fail(f"Your fork has no branch `{br}`.", f"`git switch {br}` → `git push -u origin {br}`.")
    f = parse_fields(c.g.show(br, "app/config.txt"))
    if f.get("theme") != "dark":
        return fail(f"On `{br}`, `app/config.txt` should say `theme: dark`.", "Commit it on the feature branch and push.")
    if f.get("accent", "").lower() != "purple":
        return fail(f"On `{br}`, the `accent: purple` line is missing. Your stashed work never came back.",
                    f"`git switch {br}` → `git stash list` → `git stash pop` → commit → `git push`.")
    return ok()


# ---------------------------------------------------------------------------
# Level 4 — Squash (interactive rebase)
# ---------------------------------------------------------------------------
def check_squash(c: Ctx):
    msg = c.cfg["squash_message"]
    up_tip = c.up_branch(c.cfg["messy_branch"])
    up_main = c.up.rev(c.up_ref)
    base = (c.up.out("merge-base", up_tip, up_main) or "").strip()
    paths = c.up.names_between(base, up_tip)
    messy = c.up.rev_list(f"{base}..{up_tip}")
    tip = c.g.rev("feature/login")
    if not tip:
        return fail("Your fork has no branch `feature/login`.",
                    f"`git fetch upstream` → `git switch -c feature/login upstream/{c.cfg['messy_branch']}` → `git rebase -i {c.main}` → `git push -u origin feature/login`.")
    if any(c.g.is_ancestor(m, tip) for m in messy if c.g.rev(m)):
        return fail("`feature/login` still contains HQ's 5 messy commits.",
                    f"`git switch feature/login` → `git rebase -i {c.main}` → keep the first `pick`, change the others to `squash` → message `{msg}` → `git push --force-with-lease`.")
    touching = [s for s in c.own_commits(tip) if set(c.g.files_of(s)) & set(paths)]
    if len(touching) != 1:
        return fail(f"I expected exactly **1** commit with the login work on `feature/login`, I count {len(touching)}.",
                    "Squash them: `git rebase -i <the commit before them>`, `pick` the first, `squash` the rest.")
    sha = touching[0]
    subj = c.g.subject(sha)
    if subj.strip().lower() != msg.lower():
        return fail(f"The squashed commit is called `{subj}`. It should be exactly `{msg}`.",
                    "Rename it: `git switch feature/login` → `git commit --amend` (if it's the last commit) → `git push --force-with-lease`.")
    if c.g.files_of(sha) != paths:
        return fail("The squashed commit doesn't change exactly the login files: " + ", ".join(f"`{p}`" for p in c.g.files_of(sha)),
                    f"It should touch only: {', '.join(f'`{p}`' for p in paths)}.")
    for p in paths:
        if c.g.blob(sha, p) != c.up.blob(up_tip, p):
            return fail(f"`{p}` in your squashed commit differs from HQ's final version. Some work got lost or changed.",
                        "Squash keeps all changes: use `squash`/`fixup`, never `drop`. Start again from `upstream/messy/login`.")
    parent = (c.g.parents(sha) or [""])[0]
    if parent in c.upstream_commits():
        return fail(f"Your squashed commit still sits on HQ's old `main`, not on top of **your** `{c.main}`.",
                    f"`git rebase -i {c.main}` from `feature/login` moves it on top of your main while squashing. Then `git push --force-with-lease`.")
    if not c.g.is_ancestor(parent, c.main):
        return fail(f"Your squashed commit isn't based on your `{c.main}`.",
                    f"`git switch feature/login` → `git rebase {c.main}` → `git push --force-with-lease`.")
    return ok(sha=sha)


# ---------------------------------------------------------------------------
# Level 5 — Surgical Pick (cherry-pick)
# ---------------------------------------------------------------------------
def experimental(c: Ctx):
    exp = c.up_branch(c.cfg["experimental_branch"])
    commits = c.up.rev_list(f"{c.up.rev(c.up_ref)}..{exp}")
    sec = next(s for s in commits if c.up.subject(s).lower().startswith(c.cfg["security_subject"].lower()))
    return exp, commits, sec


def check_pick(c: Ctx):
    exp, commits, sec = experimental(c)
    if any(c.g.rev(s) and c.g.is_ancestor(s, c.main) for s in commits):
        return fail("Your `main` contains HQ's experimental commits: you merged the whole branch.",
                    f"Undo: `git reset --hard <your commit before the merge>` → `git push --force-with-lease`, then cherry-pick only the fix.")
    if c.g.blob(c.main, "app/confetti.js"):
        return fail("`app/confetti.js` is on your `main`: that's an experiment, not the security fix.",
                    "Remove it (`git revert <that commit>`), then cherry-pick only the fix.")
    if c.g.blob(c.main, "app/style.css") != c.up.blob(c.up_ref, "app/style.css"):
        return fail("`app/style.css` changed on your `main`: Comic Sans is an experiment, not the security fix.",
                    "`git revert <that commit>`, then cherry-pick only the fix.")
    target = c.up.patch_id(sec)
    for s in c.own_commits(c.main):
        if "app/greet.js" in c.g.files_of(s) and c.g.patch_id(s) == target:
            return ok(sha=s)
    if c.g.blob(c.main, "app/greet.js") == c.up.blob(sec, "app/greet.js"):
        return ok()
    return fail("The XSS fix for `app/greet.js` isn't on your `main` yet.",
                f"`git log --oneline {c.main}..upstream/{c.cfg['experimental_branch']}` → find `{c.cfg['security_subject']}` → `git cherry-pick <hash>` → push.")


# ---------------------------------------------------------------------------
# Level 6 — Ship v1.0.0
# ---------------------------------------------------------------------------
def check_ship(c: Ctx):
    msg, tag = c.cfg["squash_message"], c.cfg["release_tag"]
    first_parent = c.g.rev_list("--first-parent", c.main)
    login = [s for s in first_parent if c.g.subject(s).strip().lower() == msg.lower() and len(c.g.parents(s)) == 1]
    if not login:
        merged = [s for s in c.g.rev_list(c.main) if c.g.subject(s).strip().lower() == msg.lower()]
        if merged:
            return fail("`feature/login` reached `main` through a merge commit. This level wants a straight, linear history.",
                        f"`git reset --hard HEAD~1` on main (drops the merge) → `git switch feature/login` → `git rebase {c.main}` → `git switch {c.main}` → `git merge --ff-only feature/login` → `git push --force-with-lease`.")
        return fail(f"`{msg}` isn't on `main` yet.",
                    f"`git switch feature/login` → `git rebase {c.main}` → `git switch {c.main}` → `git merge --ff-only feature/login` → `git push`.")
    ref = c.g.out("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")
    if not ref:
        return fail(f"No tag `{tag}` on your fork.", f"`git tag -a {tag} -m \"…\"` on main → `git push origin {tag}` (tags aren't pushed by `git push`).")
    if (c.g.out("cat-file", "-t", ref.strip()) or "").strip() != "tag":
        return fail(f"`{tag}` is a **lightweight** tag: no author, no date, no message.",
                    f"`git tag -d {tag}` → `git push origin :refs/tags/{tag}` → `git tag -a {tag} -m \"…\"` → `git push origin {tag}`.")
    tagged = c.g.rev(f"refs/tags/{tag}")
    if not c.g.is_ancestor(tagged, c.main):
        return fail(f"`{tag}` points to a commit that isn't on `main`.", "Tag the tip of `main`.")
    _, _, sec = experimental(c)
    if not c.g.blob(tagged, "app/login.js") or c.g.blob(tagged, "app/greet.js") != c.up.blob(sec, "app/greet.js"):
        return fail(f"`{tag}` was created before the login feature and the security fix were on `main`.",
                    f"Move it: `git tag -d {tag}` → `git push origin :refs/tags/{tag}` → tag the latest main again → push the tag.")
    if c.api is None:
        return ok()
    rel = c.api.release(c.fork, tag)
    if not rel:
        return fail(f"The tag is there, but there's no **Release** for `{tag}` on GitHub.",
                    f"Your fork → Releases → Draft a new release → choose `{tag}` → Generate release notes → Publish.")
    if rel.get("draft"):
        return fail(f"The `{tag}` release is still a draft.", "Open it → Edit → **Publish release**.")
    return ok()


CHECKS = {
    "s2-clean": check_clean,
    "s2-keymaster": check_keymaster,
    "s2-hotfix": check_hotfix,
    "s2-squash": check_squash,
    "s2-pick": check_pick,
    "s2-ship": check_ship,
}
