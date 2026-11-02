#!/usr/bin/env python3
"""
Git Quest season 2 — the Quest Master bot.

Runs in the HQ repository only, on:
  * issues: opened          → "[QUEST] …" (solo) or "[RAID] …" (team) issue
  * issue_comment: created  → "/check"
Solo: only the issue author can /check. Raid: any member listed in the team's TEAM.md.

Security model
  * flags = md5(QUEST_SALT : level : login)  (solo)  /  md5(QUEST_SALT : level : team repo)  (raid)
  * forks and team repos are cloned *bare*: no checkout, no hooks, no code executed.
  * untrusted text is only read from the event JSON, never passed to a shell.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from checks import CHECKS, Ctx, Git, fail  # noqa: E402
from raid import RAID_CHECKS, RaidCtx  # noqa: E402

CFG = json.loads((HERE / "quest.json").read_text(encoding="utf-8"))
LEVELS, RAID = CFG["levels"], CFG["raid_levels"]
API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
GIT_BASE = os.environ.get("QUEST_GIT_BASE", "https://github.com")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
SALT = os.environ.get("QUEST_SALT", "")
FLAG_MODE = (os.environ.get("FLAG_MODE") or "per-user").strip().lower()
UPSTREAM = os.environ.get("GITHUB_REPOSITORY", "")
HQ_OWNER = UPSTREAM.split("/")[0] if UPSTREAM else ""
REPO_NAME = UPSTREAM.split("/")[-1] if UPSTREAM else "git-quest-2"
LAST = LEVELS[-1]["n"]
RAID_LAST, RAID_CORE = RAID[-1]["n"], RAID[-2]["n"]   # last raid level is a bonus
REPO_RE = re.compile(r"github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9._-]+?)(?:\.git)?(?:[/#?\s)]|$)")


# ---------------------------------------------------------------------------
# GitHub REST
# ---------------------------------------------------------------------------
class Api:
    def __init__(self, token):
        self.token = token

    def req(self, method, path, body=None, ok404=False):
        url = path if path.startswith("http") else API + path
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(url, data=data, method=method, headers={
            "Accept": "application/vnd.github+json", "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "git-quest-bot"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                txt = resp.read().decode()
                return json.loads(txt) if txt else {}
        except urllib.error.HTTPError as e:
            if ok404 and e.code in (404, 410):
                return None
            print(f"::warning::GitHub API {method} {path} → {e.code} {e.read()[:300]!r}")
            raise

    def get(self, path):
        return self.req("GET", path, ok404=True)

    def paged(self, path, pages=3):
        out = []
        for page in range(1, pages + 1):
            sep = "&" if "?" in path else "?"
            items = self.get(f"{path}{sep}per_page=100&page={page}") or []
            out += items
            if len(items) < 100:
                break
        return out

    # writes on HQ
    def comment(self, repo, number, body):
        return self.req("POST", f"/repos/{repo}/issues/{number}/comments", {"body": body})

    def add_labels(self, repo, number, labels):
        return self.req("POST", f"/repos/{repo}/issues/{number}/labels", {"labels": labels})

    def react(self, repo, comment_id, content="eyes"):
        try:
            self.req("POST", f"/repos/{repo}/issues/comments/{comment_id}/reactions", {"content": content})
        except Exception:
            pass

    def close(self, repo, number):
        self.req("PATCH", f"/repos/{repo}/issues/{number}", {"state": "closed"})

    def issues(self, repo, label, creator=None):
        q = f"/repos/{repo}/issues?labels={label}&state=all" + (f"&creator={creator}" if creator else "")
        return [i for i in self.paged(q) if "pull_request" not in i]

    # reads anywhere
    def forks_of(self, repo, login):
        for f in self.paged(f"/repos/{repo}/forks", pages=5):
            if f["owner"]["login"].lower() == login.lower():
                return f["full_name"]
        return None

    def repo(self, repo):
        return self.get(f"/repos/{repo}")

    def commit(self, repo, sha):
        return self.get(f"/repos/{repo}/commits/{sha}")

    def release(self, repo, tag):
        return self.get(f"/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}")

    def pulls(self, repo):
        return self.paged(f"/repos/{repo}/pulls?state=closed")

    def reviews(self, repo, n):
        return self.paged(f"/repos/{repo}/pulls/{n}/reviews", pages=1)

    def pr_files(self, repo, n):
        return self.paged(f"/repos/{repo}/pulls/{n}/files", pages=1)

    def branch_rules(self, repo, branch):
        return self.get(f"/repos/{repo}/rules/branches/{urllib.parse.quote(branch)}")

    def check_runs(self, repo, sha):
        r = self.get(f"/repos/{repo}/commits/{sha}/check-runs?per_page=50")
        return (r or {}).get("check_runs", [])


# ---------------------------------------------------------------------------
# flags & text
# ---------------------------------------------------------------------------
def flag(level_id, who):
    seed = f"{SALT}:{level_id}" if FLAG_MODE == "static" else f"{SALT}:{level_id}:{who.lower()}"
    return f"{CFG['flag_prefix']}{{{hashlib.md5(seed.encode()).hexdigest()}}}"


def render(text, **kw):
    kw.setdefault("upstream", UPSTREAM)
    kw.setdefault("repo", REPO_NAME)
    kw.setdefault("hq", HQ_OWNER)
    for k, v in kw.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def mission(folder, n, **kw):
    f = next(HERE.joinpath(folder).glob(f"{n:02d}-*.md"))
    return render(f.read_text(encoding="utf-8"), **kw)


def bar(levels, earned, last_bonus=True):
    cells = "".join("🟩" if lv["n"] in earned else ("⭐" if last_bonus and lv is levels[-1] else "⬜") for lv in levels)
    core = len([lv for lv in levels[:-1] if lv["n"] in earned]) if last_bonus else len([lv for lv in levels if lv["n"] in earned])
    total = len(levels) - (1 if last_bonus else 0)
    return f"{cells}  **{core}/{total}**" + ("  + ⭐ bonus" if last_bonus and levels[-1]["n"] in earned else "")


# ---------------------------------------------------------------------------
# cloning
# ---------------------------------------------------------------------------
def bare_clone(full, dest, pulls=False):
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    p = subprocess.run(["git", "clone", "--bare", "--quiet", f"{GIT_BASE}/{full}.git", dest],
                       capture_output=True, text=True, timeout=180, env=env)
    if p.returncode != 0:
        return False
    if pulls:
        subprocess.run(["git", "--git-dir", dest, "fetch", "--quiet", "origin", "+refs/pull/*/head:refs/pull/*/head"],
                       capture_output=True, text=True, timeout=180, env=env)
    return True


def find_fork(api, login, workdir):
    first = f"{login}/{REPO_NAME}"
    dest = os.path.join(workdir, "fork.git")
    if bare_clone(first, dest):
        return first, dest
    other = api.forks_of(UPSTREAM, login) if api else None
    if other and other != first and bare_clone(other, dest):
        return other, dest
    return None, None


def is_real_fork(fork_git, upstream_git):
    up_roots = set((Git(upstream_git).out("rev-list", "--max-parents=0", "HEAD") or "").split())
    fork_roots = set((Git(fork_git).out("rev-list", "--max-parents=0", "--all") or "").split())
    return bool(up_roots) and up_roots <= fork_roots


# ---------------------------------------------------------------------------
# solo quest
# ---------------------------------------------------------------------------
def earned_from(labels, prefix):
    out = set()
    for l in labels:
        if l.startswith(prefix) and l[len(prefix):].isdigit():
            out.add(int(l[len(prefix):]))
    return out


def run_solo(api, login, labels, upstream_git, workdir, up_ref="HEAD", up_prefix="origin/"):
    earned = earned_from(labels, "level-")
    new, failure = [], None
    fork, fork_git = find_fork(api, login, workdir)
    if not fork:
        return new, (0, fail(f"I couldn't find a fork of `{UPSTREAM}` owned by **@{login}**.",
                             f"Click **Fork** on https://github.com/{UPSTREAM} (keep the name `{REPO_NAME}`), then comment `/check`.")), earned, None
    if not is_real_fork(fork_git, upstream_git):
        return new, (0, fail(f"`{fork}` exists but doesn't share history with `{UPSTREAM}`.",
                             "Delete it and use the **Fork** button.")), earned, fork
    if 0 not in earned:
        new.append(0)
        earned.add(0)
    ctx = Ctx(login, fork, fork_git, upstream_git, up_ref, CFG, api=api, upstream_repo=UPSTREAM, up_prefix=up_prefix)
    for lv in LEVELS[1:]:
        if lv["n"] in earned:
            continue
        try:
            res = CHECKS[lv["id"]](ctx)
        except Exception as e:
            print(f"::warning::check {lv['id']} crashed: {e!r}")
            res = fail("The checker hit an unexpected situation in your repository.",
                       "Comment `/check` again; if it persists, call an organizer.")
        if not res.ok:
            failure = (lv["n"], res)
            break
        new.append(lv["n"])
        earned.add(lv["n"])
    return new, failure, earned, fork


# ---------------------------------------------------------------------------
# team raid
# ---------------------------------------------------------------------------
def raid_repo_from(body):
    for owner, name in REPO_RE.findall(body or ""):
        if f"{owner}/{name}".lower() != UPSTREAM.lower():
            return f"{owner}/{name}"
    return None


def run_raid(api, repo, requester, labels, workdir, authorize=None):
    earned = earned_from(labels, "raid-")
    new, failure = [], None
    dest = os.path.join(workdir, "team.git")
    if not bare_clone(repo, dest, pulls=True):
        return new, (1, fail(f"I can't clone `{repo}`.", "Check the URL in the issue and that the repository is **public**.")), earned, None
    ctx = RaidCtx(repo, dest, api, CFG, HQ_OWNER, requester)
    if authorize is not None and not authorize(ctx):
        return None, None, earned, ctx
    for lv in RAID:
        if lv["n"] in earned:
            continue
        try:
            res = RAID_CHECKS[lv["id"]](ctx)
        except Exception as e:
            print(f"::warning::raid check {lv['id']} crashed: {e!r}")
            res = fail("The checker hit an unexpected situation in your team repository.",
                       "Comment `/check` again; if it persists, call an organizer.")
        if not res.ok:
            failure = (lv["n"], res)
            break
        new.append(lv["n"])
        earned.add(lv["n"])
    return new, failure, earned, ctx


# ---------------------------------------------------------------------------
def reply(n_kind, levels, folder, who_flag, new, failure, earned, fresh, last_bonus, **kw):
    by_n = {lv["n"]: lv for lv in levels}
    parts = []
    for n in new:
        lv = by_n[n]
        parts.append(f"### Level {n} cleared — {lv['title']}\n<sub>skills: {lv['skills']}</sub>\n\n```\n{flag(lv['id'], who_flag)}\n```")
    parts.append(bar(levels, earned, last_bonus))
    if failure:
        n, res = failure
        first_attempt = bool(new) or fresh
        if folder == "levels" and n == 0:
            parts.append(f"### 🔴 {res.reason}\n\n💡 {res.hint}")
        elif first_attempt:
            parts.append("---\n" + mission(folder, n, **kw))
        else:
            parts.append(f"### 🔴 {n_kind} {n} — {by_n[n]['title']}: not yet\n\n**What I see:** {res.reason}\n\n💡 **Hint:** {res.hint}\n\n"
                         f"<details><summary>Re-read the {n_kind} {n} briefing</summary>\n\n{mission(folder, n, **kw)}\n</details>")
    else:
        parts.append(mission(folder, 99, **kw))
    parts.append("<sub>🤖 Comment <code>/check</code> on this issue any time to re-run the checks.</sub>")
    return "\n\n".join(parts)


def main():
    if not SALT:
        print("::error::QUEST_SALT secret is missing — refusing to hand out flags.")
        sys.exit(1)
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    name = os.environ["GITHUB_EVENT_NAME"]
    api = Api(TOKEN)
    upstream_git = os.path.join(os.environ.get("GITHUB_WORKSPACE", "."), ".git")
    issue = event["issue"]
    title = issue.get("title", "")
    kind = "raid" if title.startswith("[RAID]") else "quest" if title.startswith("[QUEST]") else None
    if kind is None:
        return
    author = issue["user"]["login"]
    actor = author if name == "issues" else event["comment"]["user"]["login"]
    labels = [l["name"] for l in issue.get("labels", [])]

    if name == "issue_comment":
        if not event["comment"]["body"].strip().startswith("/check"):
            return
        if kind == "quest" and actor != author:
            return
    elif name != "issues":
        return

    if name == "issues":
        mine = [i for i in api.issues(UPSTREAM, kind, creator=author) if i["number"] != issue["number"]]
        if kind == "quest" and mine:
            api.comment(UPSTREAM, issue["number"], f"👋 @{author} you already have a quest running in #{mine[-1]['number']}. Continue there! Closing this one.")
            api.close(UPSTREAM, issue["number"])
            return
        if kind not in labels:
            api.add_labels(UPSTREAM, issue["number"], [kind])

    workdir = tempfile.mkdtemp(prefix="quest-")
    try:
        if kind == "quest":
            if name == "issue_comment":
                api.react(UPSTREAM, event["comment"]["id"], "eyes")
            new, failure, earned, fork = run_solo(api, author, labels, upstream_git, workdir)
            if new:
                api.add_labels(UPSTREAM, issue["number"], [f"level-{n}" for n in new] + (["finished"] if LAST in new else []))
            body = reply("Level", LEVELS, "levels", author, new, failure, earned, fresh=name == "issues",
                         last_bonus=False, login=author, fork=fork or f"{author}/{REPO_NAME}")
            if name == "issues":
                body = render((HERE / "levels" / "welcome.md").read_text(encoding="utf-8"), login=author) + "\n\n" + body
            api.comment(UPSTREAM, issue["number"], (f"@{author}\n\n" if name == "issues" else "") + body)
            print(f"quest login={author} fork={fork} new={new} earned={sorted(earned)} failure={failure[0] if failure else None}")
            return

        repo = raid_repo_from(issue.get("body"))
        if not repo:
            api.comment(UPSTREAM, issue["number"], f"@{author} I can't find your team repository link in this issue. Edit the issue and paste it (`https://github.com/<captain>/<repo>`), then comment `/check`.")
            return
        if name == "issues":
            others = [i for i in api.issues(UPSTREAM, "raid") if i["number"] != issue["number"] and (raid_repo_from(i.get("body")) or "").lower() == repo.lower()]
            if others:
                api.comment(UPSTREAM, issue["number"], f"👋 `{repo}` is already registered in #{others[0]['number']}. Continue there! Closing this one.")
                api.close(UPSTREAM, issue["number"])
                return

        def authorize(ctx):
            return actor.lower() == author.lower() or actor.lower() in ctx.members_lower()

        new, failure, earned, ctx = run_raid(api, repo, actor, labels, workdir, authorize=authorize)
        if new is None:
            print(f"raid: {actor} is not a member of {repo}; ignored")
            return
        if name == "issue_comment":
            api.react(UPSTREAM, event["comment"]["id"], "eyes")
        if new:
            api.add_labels(UPSTREAM, issue["number"], [f"raid-{n}" for n in new] + (["raid-finished"] if RAID_CORE in new else []))
        body = reply("Stage", RAID, "raid", repo, new, failure, earned, fresh=name == "issues", last_bonus=True,
                     team=repo, login=actor, captain=repo.split("/")[0])
        if name == "issues":
            body = render((HERE / "raid" / "welcome.md").read_text(encoding="utf-8"), team=repo, login=author) + "\n\n" + body
        api.comment(UPSTREAM, issue["number"], body)
        print(f"raid repo={repo} actor={actor} new={new} earned={sorted(earned)} failure={failure[0] if failure else None}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    main()
