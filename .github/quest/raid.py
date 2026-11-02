"""
Git Quest season 2 — team raid checks.

A team repository is created from the HQ raid template. The bot reads it through
a bare clone (plus the pull request refs) and the public GitHub API: pull requests,
reviews, rulesets, releases, check runs. Nothing from the team repo is executed.
"""
import re
from datetime import datetime

from checks import Git, Result, fail, ok, parse_fields, MARKER_RE


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


class RaidCtx:
    def __init__(self, repo, git_dir, api, config, hq_owner, requester):
        self.repo = repo                      # "captain/raid-name"
        self.g = Git(git_dir)
        self.api = api
        self.cfg = config
        self.hq_owner = hq_owner
        self.requester = requester
        self.main = config.get("default_branch", "main")
        self._prs = None
        self._reviews = {}
        self._files = {}

    # -- team ---------------------------------------------------------------
    def team(self):
        text = self.g.show(self.main, "TEAM.md") or ""
        members, section = [], None
        for line in text.splitlines():
            h = re.match(r"^\s*#+\s*(.+?)\s*$", line)
            if h:
                section = h.group(1).lower()
                continue
            m = re.match(r"^\s*[-*]\s*@?([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))\s*$", line)
            if m and section and "member" in section:
                members.append(m.group(1))
        name = parse_fields(text).get("team", "")
        seen, uniq = set(), []
        for m in members:
            if m.lower() not in seen:
                seen.add(m.lower())
                uniq.append(m)
        return name, uniq

    def members_lower(self):
        return {m.lower() for m in self.team()[1]}

    # -- pull requests -------------------------------------------------------
    def merged_prs(self):
        if self._prs is None:
            prs = self.api.pulls(self.repo) or []
            self._prs = sorted([p for p in prs if p.get("merged_at") and (p.get("base") or {}).get("ref") == self.main],
                               key=lambda p: p["merged_at"])
        return self._prs

    def reviews(self, n):
        if n not in self._reviews:
            self._reviews[n] = self.api.reviews(self.repo, n) or []
        return self._reviews[n]

    def files(self, n):
        if n not in self._files:
            self._files[n] = self.api.pr_files(self.repo, n) or []
        return self._files[n]

    def approved_by_teammate(self, pr):
        author = pr["user"]["login"].lower()
        team = self.members_lower()
        return any(r["state"] == "APPROVED" and r["user"]["login"].lower() in team and r["user"]["login"].lower() != author
                   for r in self.reviews(pr["number"]))


# ---------------------------------------------------------------------------
def check_assemble(c: RaidCtx):
    info = c.api.repo(c.repo)
    if not info:
        return fail(f"I can't open `{c.repo}`. Is it public?", "Settings → General → Danger Zone → Change visibility → Public.")
    if info.get("private"):
        return fail(f"`{c.repo}` is private. The bot (and your classmates) can't see it.", "Make it public.")
    tpl = ((info.get("template_repository") or {}).get("full_name") or "").lower()
    want = f"{c.hq_owner}/{c.cfg['raid_template']}".lower()
    if tpl != want:
        return fail(f"`{c.repo}` wasn't created from the `{want}` template.",
                    f"Open github.com/{want} → **Use this template** → Create a new repository (public).")
    name, members = c.team()
    if not name or name.upper() == "TBD":
        return fail("`TEAM.md` has no team name yet (`team: TBD`).", "Edit `TEAM.md`: `team: <your team name>`.")
    if not 3 <= len(members) <= 5:
        return fail(f"`TEAM.md` lists {len(members)} member(s) under **Members**. A raid team is 3 to 5 people.",
                    "One line per member: `- @github-username`.")
    if c.requester.lower() not in c.members_lower():
        return fail(f"@{c.requester} isn't listed in `TEAM.md`.", "Add yourself under **Members**: `- @your-username`.")
    rules = c.api.branch_rules(c.repo, c.main) or []
    pr_rule = next((r for r in rules if r.get("type") == "pull_request"), None)
    if not pr_rule:
        return fail(f"`{c.main}` isn't protected: anyone can push straight to it.",
                    "Captain: Settings → Rules → Rulesets → New branch ruleset → Enforcement **Active** → Target: **Include default branch** → ✅ Require a pull request before merging (1 approval) → Create.")
    if int((pr_rule.get("parameters") or {}).get("required_approving_review_count", 0)) < 1:
        return fail("Your ruleset requires a pull request, but **0** approvals.",
                    "Edit the ruleset → Require a pull request before merging → Required approvals: **1**.")
    return ok()


def check_ships(c: RaidCtx):
    _, members = c.team()
    missing, unapproved = [], []
    for m in members:
        prs = [p for p in c.merged_prs() if p["user"]["login"].lower() == m.lower()
               and any(f["filename"].lower() == f"members/{m.lower()}.md" for f in c.files(p["number"]))]
        if not prs:
            missing.append(m)
        elif not any(c.approved_by_teammate(p) for p in prs):
            unapproved.append(m)
    if missing:
        return fail("No merged pull request adding `members/<login>.md` yet from: " + ", ".join(f"@{m}" for m in missing) + ".",
                    "Each member: branch → add `members/<your-login>.md` → push → open a PR → a teammate approves → merge.")
    if unapproved:
        return fail("These PRs were merged without a teammate's approval: " + ", ".join(f"@{m}" for m in unapproved) + ".",
                    "Your ruleset should block that. Check it's **Active**, then redo that member's file in a new, approved PR.")
    return ok()


def check_review(c: RaidCtx):
    team = c.members_lower()
    for p in c.merged_prs():
        author = p["user"]["login"].lower()
        revs = sorted(c.reviews(p["number"]), key=lambda r: r.get("submitted_at") or "")
        crs = [r for r in revs if r["state"] == "CHANGES_REQUESTED" and r["user"]["login"].lower() in team and r["user"]["login"].lower() != author]
        for cr in crs:
            later_ok = [r for r in revs if r["state"] == "APPROVED" and ts(r.get("submitted_at")) and ts(r["submitted_at"]) > ts(cr["submitted_at"])
                        and r["user"]["login"].lower() in team and r["user"]["login"].lower() != author]
            if later_ok and cr.get("commit_id") != p["head"]["sha"]:
                return ok(pr=p["number"])
    any_cr = any(r["state"] == "CHANGES_REQUESTED" for p in c.merged_prs() for r in c.reviews(p["number"]))
    if any_cr:
        return fail("I see a **Request changes** review, but not the rest: new commits pushed after it, then an approval, then the merge.",
                    "The author pushes a fix to the **same branch** (the PR updates itself), then the reviewer approves.")
    return fail("No merged PR went through **Request changes** yet.",
                "On an open PR: Files changed → comment on a line → Review changes → **Request changes**. The author fixes and pushes; the reviewer approves; merge.")


def check_collision(c: RaidCtx):
    touching = []
    for p in c.merged_prs():
        for f in c.files(p["number"]):
            if f["filename"] == "mission.md" and re.search(r"^\+\s*target\s*:", f.get("patch") or "", re.M):
                touching.append(p)
                break
    authors = {p["user"]["login"].lower() for p in touching}
    if len(touching) < 2 or len(authors) < 2:
        return fail(f"I need 2 merged PRs from **2 different members** that both change the `target:` line of `mission.md`. I see {len(touching)}.",
                    "Two members branch from the same `main` and each edits `target:`. Merge the first; the second PR then shows a conflict.")
    for i, a in enumerate(touching):
        for b in touching[i + 1:]:
            if b["user"]["login"].lower() == a["user"]["login"].lower():
                continue
            head = c.g.rev(f"refs/pull/{b['number']}/head") or c.g.rev(b["head"]["sha"])
            if head and a.get("merge_commit_sha") and c.g.rev(a["merge_commit_sha"]) and c.g.is_ancestor(a["merge_commit_sha"], head):
                markers = c.g.out("grep", "-I", "-n", "-E", MARKER_RE, c.main, "--", ".", ":(exclude).github")
                if markers:
                    return fail("Conflict markers were merged into `main`: `" + markers.splitlines()[0].split(":", 2)[-1] + "`",
                                "Open a PR that removes them.")
                target = parse_fields(c.g.show(c.main, "mission.md")).get("target", "")
                if not target or target.upper() == "TBD":
                    return fail("`mission.md` on main still says `target: TBD`.", "The resolved line should keep both proposals.")
                return ok(first=a["number"], second=b["number"])
    return fail("Both PRs changed `target:`, but the second one never took `main`'s new version before merging.",
                "Recreate the collision: two new branches from the same `main`, both edit `target:`. After merging the first, update the second branch: `git pull origin main --no-rebase` → resolve → push (or the PR's **Resolve conflicts** button).")


def check_release(c: RaidCtx):
    tag = c.cfg["release_tag"]
    ref = c.g.out("rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")
    if not ref:
        return fail(f"No tag `{tag}` in `{c.repo}`.", f"`git switch main && git pull` → `git tag -a {tag} -m \"…\"` → `git push origin {tag}`.")
    if (c.g.out("cat-file", "-t", ref.strip()) or "").strip() != "tag":
        return fail(f"`{tag}` is a lightweight tag.", f"Delete it (`git tag -d {tag}` + `git push origin :refs/tags/{tag}`), recreate it with `-a`, push.")
    if not c.g.is_ancestor(c.g.rev(f"refs/tags/{tag}"), c.main):
        return fail(f"`{tag}` isn't on `main`.", "Tag a commit of `main`.")
    rel = c.api.release(c.repo, tag)
    if not rel or rel.get("draft"):
        return fail(f"No published Release for `{tag}`.", "Releases → Draft a new release → choose the tag → **Generate release notes** → Publish.")
    if len((rel.get("body") or "").strip()) < 10:
        return fail("The release has no notes.", "Edit the release → **Generate release notes** (or write what changed) → Update.")
    return ok()


def check_gate(c: RaidCtx):
    rules = c.api.branch_rules(c.repo, c.main) or []
    rsc = next((r for r in rules if r.get("type") == "required_status_checks"), None)
    ctxs = [x.get("context", "") for x in ((rsc or {}).get("parameters") or {}).get("required_status_checks", [])]
    if "validate" not in ctxs:
        return fail("Your ruleset doesn't require the `validate` check yet.",
                    "Edit the ruleset → ✅ Require status checks to pass → Add checks → `validate` → Save.")
    for p in reversed(c.merged_prs()):
        runs = c.api.check_runs(c.repo, p["head"]["sha"]) or []
        if any(r.get("name") == "validate" and r.get("conclusion") == "success" for r in runs):
            return ok(pr=p["number"])
    return fail("No merged PR has a green `validate` check yet.", "Open one more PR (any small change), wait for ✅ validate, get it approved, merge.")


RAID_CHECKS = {
    "raid-assemble": check_assemble,
    "raid-ships": check_ships,
    "raid-review": check_review,
    "raid-collision": check_collision,
    "raid-release": check_release,
    "raid-gate": check_gate,
}
