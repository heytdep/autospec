#!/usr/bin/env python3
"""AutoSpec dashboard server. Python stdlib only."""

import http.server
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

AUTOSPEC_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = Path(os.environ.get("AUTOSPEC_RUNS_DIR", AUTOSPEC_ROOT / "runs"))
DASHBOARD_DIR = AUTOSPEC_ROOT / "dashboard"
JOBS_DIR = Path(os.environ.get("AUTOSPEC_JOBS_DIR", "")) if os.environ.get("AUTOSPEC_JOBS_DIR") else None


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def read_text(path):
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return None


def list_runs():
    if not RUNS_DIR.exists():
        return []
    runs = []
    for d in sorted(RUNS_DIR.iterdir()):
        if d.is_dir():
            status = read_json(d / "status.json") or {}
            runs.append({"id": d.name, "status": status.get("state", "unknown")})
    return runs


def get_compartments(run_id):
    return read_json(RUNS_DIR / run_id / "compartments.json")


def get_registry(run_id):
    return read_json(RUNS_DIR / run_id / "registry.json")


def get_status(run_id):
    return read_json(RUNS_DIR / run_id / "status.json")


def get_journals(run_id, compartment_id=None):
    run_dir = RUNS_DIR / run_id
    journals = []

    if compartment_id:
        dirs = [run_dir / compartment_id]
    else:
        dirs = [d for d in run_dir.iterdir() if d.is_dir() and d.name.startswith("C")]

    for d in dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.name.startswith("step_") and f.suffix == ".json":
                j = read_json(f)
                if j:
                    journals.append(j)

    journals.sort(key=lambda x: x.get("step", 0))
    return journals


def get_checkpoints(run_id, compartment_id):
    d = RUNS_DIR / run_id / compartment_id
    checkpoints = []
    if not d.exists():
        return checkpoints
    for f in sorted(d.iterdir()):
        if f.name.startswith("checkpoint_") and f.suffix == ".md":
            checkpoints.append({
                "name": f.name,
                "ok_only": "_ok" in f.name,
                "content": read_text(f),
            })
    return checkpoints


def get_live(run_id):
    """Infer live agent state from filesystem: which files exist in step dirs."""
    run_dir = RUNS_DIR / run_id
    status = read_json(run_dir / "status.json") or {}
    compartments = []

    for d in sorted(run_dir.iterdir()):
        if not d.is_dir() or not d.name.startswith("C"):
            continue
        comp_id = d.name

        step_dirs = sorted(
            [s for s in d.iterdir() if s.is_dir() and s.name.startswith("step_")],
            key=lambda s: s.name,
        )
        completed_journals = sorted(
            [f for f in d.iterdir() if f.name.startswith("step_") and f.suffix == ".json"],
            key=lambda f: f.name,
        )

        current_step = None
        phase = "idle"
        phase_data = {}
        elapsed_s = 0

        for sd in reversed(step_dirs):
            step_num = sd.name.replace("step_", "")
            journal_file = d / f"{sd.name}.json"
            if journal_file.exists():
                continue

            files = {f.name: f.stat().st_mtime for f in sd.iterdir() if f.is_file()}
            current_step = step_num

            if "judgment.json" in files:
                phase = "hard-gate"
                j = read_json(sd / "judgment.json")
                if j:
                    phase_data = {"ruling": j.get("ruling", ""), "reasoning": _trunc(j.get("reasoning", ""), 200)}
                elapsed_s = _elapsed(files.get("judgment.json", 0))
            elif "review.json" in files:
                phase = "judging"
                r = read_json(sd / "review.json")
                if r:
                    verdict = r.get("verdict", "")
                    summary = r.get("claim_analysis", {}).get("counterexample", "") or \
                              "; ".join(r.get("precondition_check", {}).get("issues", [])[:1])
                    phase_data = {"verdict": verdict, "summary": _trunc(summary, 300)}
                elapsed_s = _elapsed(files.get("review.json", 0))
            elif "proposal.json" in files:
                phase = "reviewing"
                p = read_json(sd / "proposal.json")
                if p:
                    phase_data = {
                        "technique": p.get("technique_name", p.get("technique", "")),
                        "claim": _trunc(p.get("claim", ""), 200),
                        "target_actions": p.get("target_actions", []),
                    }
                elapsed_s = _elapsed(files.get("proposal.json", 0))
            else:
                phase = "proposing"
                latest_mtime = max(files.values()) if files else sd.stat().st_mtime
                elapsed_s = _elapsed(latest_mtime)

            break

        if current_step is None and step_dirs:
            phase = "idle"

        compartments.append({
            "id": comp_id,
            "step": current_step,
            "phase": phase,
            "phase_data": phase_data,
            "elapsed_s": round(elapsed_s),
            "completed_steps": len(completed_journals),
        })

    status_mtime = 0
    status_path = run_dir / "status.json"
    if status_path.exists():
        status_mtime = status_path.stat().st_mtime

    return {
        "state": status.get("state", "unknown"),
        "started": status.get("started", ""),
        "config": status.get("config", {}),
        "escalation": status.get("escalation", {}),
        "compartments": compartments,
        "status_mtime": status_mtime,
    }


def _trunc(s, n):
    return s[:n] + ".." if len(s) > n else s


def _elapsed(mtime):
    import time
    return max(0, time.time() - mtime)


def list_jobs():
    if not JOBS_DIR or not JOBS_DIR.exists():
        return []
    jobs = []
    for state_dir in ["queue", "active", "completed", "failed"]:
        d = JOBS_DIR / state_dir
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix == ".md":
                content = read_text(f)
                meta = _parse_job_frontmatter(content) if content else {}
                meta["state_dir"] = state_dir
                jobs.append(meta)
    return jobs


def get_job(job_id):
    if not JOBS_DIR or not JOBS_DIR.exists():
        return None
    for state_dir in ["queue", "active", "completed", "failed"]:
        d = JOBS_DIR / state_dir
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix == ".md":
                content = read_text(f)
                meta = _parse_job_frontmatter(content) if content else {}
                if meta.get("id") == job_id:
                    meta["state_dir"] = state_dir
                    meta["body"] = content
                    return meta
    return None


def _parse_job_frontmatter(content):
    if not content or not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    import re
    meta = {}
    for line in content[3:end].strip().split("\n"):
        m = re.match(r'^(\w+):\s*(.+)$', line)
        if m:
            val = m.group(2).strip().strip('"').strip("'")
            meta[m.group(1)] = val
    return meta


def get_intersections(run_id):
    d = RUNS_DIR / run_id / "intersections"
    if not d.exists():
        return []
    updates = []
    for sub in sorted(d.iterdir()):
        if sub.is_dir():
            for f in sorted(sub.iterdir()):
                if f.suffix == ".json":
                    u = read_json(f)
                    if u:
                        u["intersection_id"] = sub.name
                        updates.append(u)
    return updates


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if not path.startswith("/api/"):
            return super().do_GET()

        parts = path.strip("/").split("/")

        try:
            data = self.route_api(parts, params)
            self.send_json(200, data)
        except FileNotFoundError:
            self.send_json(404, {"error": "not found"})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def route_api(self, parts, params):
        # /api/runs
        if parts == ["api", "runs"]:
            return list_runs()

        # /api/runs/<run_id>/compartments
        if len(parts) == 4 and parts[0:2] == ["api", "runs"] and parts[3] == "compartments":
            return get_compartments(parts[2])

        # /api/runs/<run_id>/registry
        if len(parts) == 4 and parts[0:2] == ["api", "runs"] and parts[3] == "registry":
            return get_registry(parts[2])

        # /api/runs/<run_id>/status
        if len(parts) == 4 and parts[0:2] == ["api", "runs"] and parts[3] == "status":
            return get_status(parts[2])

        # /api/runs/<run_id>/journals
        # /api/runs/<run_id>/journals/<compartment_id>
        if len(parts) >= 4 and parts[0:2] == ["api", "runs"] and parts[3] == "journals":
            comp = parts[4] if len(parts) > 4 else None
            return get_journals(parts[2], comp)

        # /api/runs/<run_id>/checkpoints/<compartment_id>
        if len(parts) == 5 and parts[0:2] == ["api", "runs"] and parts[3] == "checkpoints":
            return get_checkpoints(parts[2], parts[4])

        # /api/runs/<run_id>/intersections
        if len(parts) == 4 and parts[0:2] == ["api", "runs"] and parts[3] == "intersections":
            return get_intersections(parts[2])

        # /api/runs/<run_id>/live
        if len(parts) == 4 and parts[0:2] == ["api", "runs"] and parts[3] == "live":
            return get_live(parts[2])

        # /api/jobs
        if parts == ["api", "jobs"]:
            return list_jobs()

        # /api/jobs/<job_id>
        if len(parts) == 3 and parts[0:2] == ["api", "jobs"]:
            result = get_job(parts[2])
            if result is None:
                raise FileNotFoundError
            return result

        raise FileNotFoundError

    def send_json(self, code, data):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[autospec-dashboard] {args[0]}\n")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8420
    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    print(f"AutoSpec dashboard: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down")
        server.server_close()


if __name__ == "__main__":
    main()
