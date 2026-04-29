# Deployments

Append-only log. Add a row every time a Render rebuild completes
successfully. Roll back? Add a row noting the rollback rather than
deleting the bad entry — history of incidents is the point.

| Date (UTC)         | Version | Git SHA  | URL | Note |
|--------------------|---------|----------|-----|------|
| _yyyy-mm-dd hh:mm_ | _0.0.1_ | _abc1234_ | _https://invoice-intelligence.onrender.com_ | _example row — replace with the first real deploy_ |

## How to update this file

After Render finishes a deploy:

1. Look up the short SHA in Render's "Events" panel (or run
   `git rev-parse --short HEAD` on whatever branch was deployed).
2. Note the version from `make version`.
3. Append a row above. Keep newest at the top.
4. `git add DEPLOYMENTS.md && git commit -m "chore: log deploy 0.0.1"`.

## Why manual?

For a college project this is right-sized: zero infrastructure, fully
auditable, takes 30 seconds. The same data could be auto-emitted by a
GitHub Actions deploy step — but Render handles deploys directly, so a
hooks-based auto-log would need a separate webhook receiver. Defer
until the deploy cadence is high enough to make manual painful.

## Roll-forward / roll-back convention

Render's "Events" tab keeps the previous deploys live. To roll back:

1. Render dashboard → Service → Events → click the previous successful
   deploy → "Roll back to this deploy".
2. Append a row here with version + SHA of the deploy you rolled BACK
   TO and a `[rollback]` tag in the Note column.
