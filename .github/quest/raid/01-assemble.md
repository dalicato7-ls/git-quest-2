## Stage 1 — Assemble
*template · collaborators · ruleset*

**Captain**, in this order:

1. Open **github.com/{hq}/git-raid** → **Use this template** → **Create a new repository** → Owner: you · Name: `raid-<team-name>` · **Public** → Create.
2. In your new repo, edit `TEAM.md` on github.com (✏️): set `team: <your team name>` and list every member under **Members**, one per line: `- @github-username`. Commit directly to `main` (it's the last time anyone can).
3. Settings → **Collaborators** → Add people → each member. Members: accept the invitation (email, or github.com/notifications).
4. Settings → **Rules** → **Rulesets** → New ruleset → **New branch ruleset**:
   - Ruleset name: `protect-main` · Enforcement status: **Active**
   - Target branches → Add target → **Include default branch**
   - ✅ Restrict deletions · ✅ Block force pushes
   - ✅ **Require a pull request before merging** → Required approvals: **1**
   - Create
5. Make sure this issue links your repository, then anyone in the team comments **`/check`**.

From now on, nobody (not even the captain) can push to `main`: everything goes through a pull request.
