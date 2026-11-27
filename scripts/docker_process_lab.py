"""Reproduce Linux process recovery with Docker, without mounting a live store."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "python:3.11-slim"
WORKER = "scripts/linux_process_kill.py"
MODULES = ("framework", "shadow_runtime", "sandbox_runtime", "spec")
# Prevent proxy values from Docker client config entering lab containers.
NO_PROXY_ENV = [arg for key in ("HTTP_PROXY", "HTTPS_PROXY", "FTP_PROXY", "ALL_PROXY", "NO_PROXY")
                for spelling in (key, key.lower()) for arg in ("--env", spelling + "=")]


def command(argv, timeout=90):
    p = subprocess.run(argv, cwd=ROOT, shell=False, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       env=dict(os.environ, PYTHONUTF8="1", GIT_OPTIONAL_LOCKS="0"))
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or f"{argv[:2]} exited {p.returncode}")
    return p.stdout


def collect(directory):
    paths = set(command(["git", "ls-files", "-z", "--", *MODULES]).split("\0")) - {""}
    paths.add(WORKER)
    digests = {}
    for name in sorted(paths):
        src = ROOT / name
        if not src.is_file() or src.is_symlink() or not src.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("not an ordinary source file: " + name)
        data = src.read_bytes()
        dst = directory / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        digests[name] = hashlib.sha256(data).hexdigest()
    return hashlib.sha256(json.dumps(digests, sort_keys=True).encode()).hexdigest()


def main():
    image = json.loads(command(["docker", "image", "inspect", IMAGE]))[0]
    if image["Os"] != "linux" or command(["docker", "info", "--format", "{{.OSType}}"]).strip() != "linux":
        raise RuntimeError("Linux Docker image and daemon required")
    head = command(["git", "rev-parse", "HEAD"]).strip()
    dirty = bool(command(["git", "status", "--porcelain"]).strip())
    with tempfile.TemporaryDirectory(prefix="lingshu-container-code-") as temp:
        source_sha = collect(Path(temp))
        name = "lingshu-process-check-" + uuid.uuid4().hex
        docker = ["docker", "run", "--rm", "--name", name, "--pull", "never", "--network", "none", *NO_PROXY_ENV,
                  "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=128m,mode=1777",
                  "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--user", "65534:65534",
                  "--pids-limit", "64", "--memory", "384m",
                  "--mount", f"type=bind,source={temp},target=/exercise,readonly", image["Id"],
                  "python", "-X", "utf8", "-B", "/exercise/" + WORKER, "--isolated"]
        try:
            result = json.loads(command(docker, 120))
        except subprocess.TimeoutExpired:
            command(["docker", "kill", name], 15)
            raise
    if any([x["exit"] for x in result[name]] != [-9, -9, -9] for name in ("cases", "governance_cases")):
        raise RuntimeError("incomplete process exit evidence")
    print(json.dumps(dict(base=head, working_tree_changes=dirty, image=image["Id"], source_sha=source_sha,
                          isolation="read-only source copy; task-local tmpfs; no network; non-root", run=result), sort_keys=True))


if __name__ == "__main__":
    main()
