#!/usr/bin/env bash
# Commits storage/jobs.db if it changed and pushes immediately. Called after
# every pipeline stage (scraping, cleanup, each scored batch) instead of
# once at the very end of the workflow: a run killed by the job's timeout
# used to lose everything it had done, since nothing was pushed until the
# last step. Now a cancelled run still keeps whatever it managed to commit,
# and the next day's cron continues from there instead of from scratch.
set -euo pipefail

message="${1:?usage: commit_db.sh <commit message>}"

git config user.name "job-agent-bot"
git config user.email "actions@github.com"
git add storage/jobs.db

if git diff --cached --quiet; then
  echo "Aucun changement à committer (${message})."
else
  git commit -m "${message} [skip ci]"
  git push
fi
