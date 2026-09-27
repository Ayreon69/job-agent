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
  # Someone may have pushed to master while this run was going (a code
  # push, 2026-09-27: the first commit of a manually dispatched run was
  # rejected with "fetch first" and the job failed). Replay our commit on
  # top of it and retry. A conflict means the other push touched
  # storage/jobs.db too: stop rather than overwrite it silently.
  for attempt in 1 2 3; do
    if git push; then
      exit 0
    fi
    echo "Push refusé (tentative ${attempt}/3) : rebase sur origin puis nouvel essai."
    if ! git pull --rebase; then
      git rebase --abort || true
      echo "Conflit sur storage/jobs.db avec un push concurrent : arrêt sans écraser." >&2
      exit 1
    fi
  done
  echo "Push toujours refusé après 3 tentatives." >&2
  exit 1
fi
