## Stage 2 — Everyone Ships
*branch · pull request · approval*

**Every member**, in parallel:
```bash
git clone git@github.com:{team}.git      # or the https URL
cd <repo>
git switch -c add-<your-login>
```
Create `members/<your-login>.md` (copy `members/_template.md`):
```text
name: Your Name
role: reviewer
motto: Hack fast, defend faster
```
```bash
git add members/
git commit -m "feat: add <your-login> to the crew"
git push -u origin add-<your-login>
```
On GitHub: **Compare & pull request** (base: `main` of **your team repo**) → in *Reviewers*, pick a teammate → Create.

**Reviewer:** open the PR → **Files changed** → **Review changes** → **Approve** → Submit. Then anyone merges it.

Try to push to `main` directly once, to see the ruleset refuse it. Then **`/check`** when every member's PR is merged.
