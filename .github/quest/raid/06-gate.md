## BONUS — Gatekeeper
*required status check*

Your repo runs a workflow called **validate** on every PR: it checks that each `members/*.md` has a `name:` and a `role:`, and that no conflict markers slipped in. Make it mandatory:

1. Settings → Rules → Rulesets → `protect-main` → ✅ **Require status checks to pass** → Add checks → type `validate` → select it → Save.
2. Open a PR that breaks a member file (remove a `role:` line): watch **validate** go red and the merge button lock.
3. Fix it, push, watch it go green, get an approval, merge.

Then **`/check`**.
