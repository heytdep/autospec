---
name: poll-jobs
description: Poll the job queue, claim and execute pending jobs. Designed for `/loop 5m /poll-jobs` on the executor.
---

# Poll Jobs

Single iteration of the executor job loop. Pull the repo, check for queued jobs, execute if found.

## Procedure

### 1. Pull latest

```bash
cd $AUTOSPEC_ROOT/techniques
git pull --rebase
```

If rebase fails due to conflicts, abort and report. Do not force-push.

### 2. Check queue

List files in `jobs/queue/`. If no `.md` files exist, go to step 6 (heartbeat-only).

### 3. Claim job

Pick the oldest job file (by filename sort). Claim it:

```bash
git mv jobs/queue/<job>.md jobs/active/<job>.md
```

Update the file's YAML frontmatter:
- Set `status: active`
- Add `claimed_at: <ISO timestamp>`
- Add `executor: <hostname>`

Commit and push immediately so the publisher sees the claim:
```bash
git add jobs/active/<job>.md
git commit -m "claim job: <job_id>"
git push
```

### 4. Execute job

Read the job's instructions section. Execute based on type:

**autospec jobs:**
- Set `AUTOSPEC_RUNS_DIR=$AUTOSPEC_ROOT/techniques/runs`
- Invoke the autospec skill with the parameters from the instructions
- After each autospec step or natural breakpoint, commit and push intermediate results:
  ```bash
  cd $AUTOSPEC_ROOT/techniques
  git add runs/
  git commit -m "progress: <job_id> step N"
  git push
  ```

**arbitrary jobs:**
- Follow the markdown instructions directly
- Commit and push results at natural breakpoints

### 5. Complete or fail

**On success:**
```bash
git mv jobs/active/<job>.md jobs/completed/<job>.md
```
Update frontmatter:
- Set `status: completed`
- Add `completed_at: <ISO timestamp>`
- Add `run_id: <run_id>` (if autospec)

**On failure:**
```bash
git mv jobs/active/<job>.md jobs/failed/<job>.md
```
Update frontmatter:
- Set `status: failed`
- Add `failed_at: <ISO timestamp>`
- Add `error: "<description>"`

Commit and push:
```bash
git add jobs/
git commit -m "<completed|failed> job: <job_id>"
git push
```

### 6. Heartbeat

Update `sync/status.json`:
```json
{
  "executor_id": "<hostname>",
  "heartbeat": "<ISO timestamp>",
  "state": "idle",
  "current_job": null,
  "history": ["<last 10 job IDs>"]
}
```

During execution, set `state: "executing"` and `current_job: "<job_id>"`.

Commit and push:
```bash
git add sync/status.json
git commit -m "heartbeat"
git push
```

## Notes

- The executor processes one job at a time. If a job is running when `/loop` fires again, the new invocation should check `jobs/active/` first: if there's already an active job owned by this executor, skip to heartbeat-only (the original invocation is still handling it).
- The publisher can queue jobs at any time regardless of executor state. Queue writes and job execution never conflict (different directories, different machines).
- Always push after claiming so the publisher sees the state change immediately.
- If `git push` fails (remote ahead), pull --rebase and retry once. If still failing, log and continue.
