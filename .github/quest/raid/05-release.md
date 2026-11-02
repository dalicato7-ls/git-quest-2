## Stage 5 — Ship It
*annotated tag · release notes*

One member:
```bash
git switch main && git pull
git tag -a v1.0.0 -m "v1.0.0: crew assembled, mission set"
git push origin v1.0.0
```
Then your team repo → **Releases** → Draft a new release → tag `v1.0.0` → **Generate release notes** (it lists every merged PR) → Publish.

Then **`/check`**.
