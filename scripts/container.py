#!/usr/bin/env python3
"""Portable Docker boundary for the optional Linux runner (Python stdlib only).

Requires a running Docker engine and a prebuilt image containing git, python3,
and non-setuid Bubblewrap. Nested rootless Bubblewrap requires user namespaces
on the Docker host. Nested proc mounts also require unmasked container proc paths.
The seccomp=unconfined and systempaths=unconfined exceptions are explicit; no
capabilities or privilege are added. This is not a hostile-code security claim.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


DEFAULT_IMAGE = "anti-slop-runtime:local"


def positive(value):
    result = int(value)
    if result <= 0:
        raise argparse.ArgumentTypeError("limit must be positive")
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--image", default=DEFAULT_IMAGE)
    result.add_argument("--runner", type=Path, default=Path(__file__).resolve().parents[1],
                        help="repository containing scripts/, mounted read-only")
    result.add_argument("--memory-mib", type=positive, default=2048)
    result.add_argument("--pids", type=positive, default=256)
    result.add_argument("--cpus", type=positive, default=2)
    modes = result.add_subparsers(dest="operation", required=True)
    run = modes.add_parser("run", help="execute a run spec with read-only source")
    run.add_argument("--spec", type=Path, required=True)
    run.add_argument("--snapshot", type=Path, required=True,
                     help="dedicated empty snapshot parent; result is created in its workspace/ child")
    run.add_argument("--evidence", type=Path, required=True)
    run.add_argument("--sarif-check", help="diagnose check whose stdout is SARIF")
    run.add_argument("--sarif-tool", help="one tool name to export")
    modes.add_parser("test", help="run the complete suite including real Bubblewrap")
    execute = modes.add_parser("exec", help="run an explicit diagnostic/evaluation command in the same boundary")
    execute.add_argument("command", nargs=argparse.REMAINDER)
    execute.add_argument("--evidence", type=Path, help="dedicated writable host directory mounted at /evidence")
    return result


def _mount(path: Path, target: str, readonly: bool):
    if "," in str(path):
        raise ValueError("Docker bind paths must not contain commas")
    return ["--mount", f"type=bind,source={path},target={target}" + (",readonly" if readonly else "")]


def _check_output_directory(path: Path, uid: int, gid: int):
    if not path.is_dir():
        raise ValueError(f"output path is not a directory: {path}")
    if os.getuid() == 0:
        # Check the bind root itself, not host parents hidden by the mount.
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import os,sys; os.fchdir(int(sys.argv[1])); "
                 "sys.exit(0 if os.access('.', os.R_OK | os.W_OK | os.X_OK) else 1)",
                 str(descriptor)],
                pass_fds=(descriptor,), user=uid, group=gid, extra_groups=(),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
            )
            accessible = result.returncode == 0
        finally:
            os.close(descriptor)
    else:
        accessible = os.access(path, os.R_OK | os.W_OK | os.X_OK)
    if not accessible:
        raise ValueError(f"output directory is not readable/writable/searchable by container UID/GID {uid}:{gid}: {path}")


def _prepare_output_directory(path: Path, uid: int, gid: int):
    try:
        path.mkdir(parents=True)
    except FileExistsError:
        _check_output_directory(path, uid, gid)
        return
    # Never alter pre-existing output directories or their parents.
    if os.getuid() == 0:
        os.chown(path, uid, gid)
    path.chmod(0o700)


def docker_command(args):
    runner = args.runner.resolve(strict=True)
    if not (runner / "scripts/run.py").is_file():
        raise ValueError("--runner must contain scripts/run.py")
    uid, gid = os.getuid(), os.getgid()
    if uid == 0:
        uid, gid = 65534, 65534
    command = ["docker", "run", "--rm", "--init", "--network", "none",
               "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges=true",
               "--security-opt", "seccomp=unconfined", "--security-opt", "systempaths=unconfined",
               "--user", f"{uid}:{gid}",
               "--memory", f"{args.memory_mib}m", "--memory-swap", f"{args.memory_mib}m",
               "--pids-limit", str(args.pids), "--cpus", str(args.cpus),
               "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m,mode=1777",
               "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "HOME=/tmp/home",
               "--env", "HERMES_HOME=/evidence", "--workdir", "/runner/scripts"]
    command.extend(_mount(runner, "/runner", True))
    if args.operation == "run":
        from anti_slop_core.schema import load_run_spec
        raw_spec = args.spec.resolve(strict=True).read_bytes()
        load_run_spec(raw_spec)
        payload = json.loads(raw_spec)
        source = Path(payload["repo_path"]).resolve(strict=True)
        snapshot, evidence = args.snapshot.resolve(), args.evidence.resolve()
        for writable in (snapshot, evidence):
            if writable == source or writable.is_relative_to(source) or source.is_relative_to(writable):
                raise ValueError("snapshot/evidence must be disjoint from source")
            if writable == runner or writable.is_relative_to(runner) or runner.is_relative_to(writable):
                raise ValueError("snapshot/evidence must be disjoint from the read-only runner")
        if snapshot == evidence or snapshot.is_relative_to(evidence) or evidence.is_relative_to(snapshot):
            raise ValueError("snapshot and evidence must be disjoint")
        for writable in (snapshot, evidence):
            if writable.exists():
                _check_output_directory(writable, uid, gid)
        if snapshot.exists() and any(snapshot.iterdir()):
            raise ValueError("snapshot directory must be empty")
        _prepare_output_directory(snapshot, uid, gid)
        _prepare_output_directory(evidence, uid, gid)
        original_snapshot = Path(payload["snapshot_root"]).resolve()
        for check in payload.get("checks", []):
            cwd = Path(check.get("cwd", "."))
            if cwd.is_absolute():
                relative = cwd.resolve().relative_to(original_snapshot)
                check["cwd"] = str(Path("/snapshots/workspace") / relative)
        payload["repo_path"], payload["snapshot_root"] = "/source", "/snapshots/workspace"
        spec_name = "container-spec-" + uuid.uuid4().hex + ".json"
        with (evidence / spec_name).open("x", encoding="utf-8") as spec_file:
            if os.getuid() == 0:
                os.fchown(spec_file.fileno(), uid, gid)
            os.fchmod(spec_file.fileno(), 0o600)
            spec_file.write(json.dumps(payload) + "\n")
        command.extend(_mount(source, "/source", True))
        command.extend(_mount(snapshot, "/snapshots", False))
        command.extend(_mount(evidence, "/evidence", False))
        if os.getuid() == 0:
            # Trust only the explicitly mounted source despite its host owner.
            # Reset inherited image configuration; never trust all repositories.
            command.extend(("--env", "GIT_CONFIG_COUNT=2",
                            "--env", "GIT_CONFIG_KEY_0=safe.directory", "--env", "GIT_CONFIG_VALUE_0=",
                            "--env", "GIT_CONFIG_KEY_1=safe.directory", "--env", "GIT_CONFIG_VALUE_1=/source"))
        inner = ["/usr/bin/python3", "run.py", payload["mode"], "--spec", "/evidence/" + spec_name]
        if args.sarif_check or args.sarif_tool:
            if payload["mode"] != "diagnose" or not args.sarif_check or not args.sarif_tool:
                raise ValueError("SARIF export requires diagnosis and both --sarif-check and --sarif-tool")
            inner.extend(("--sarif-check", args.sarif_check, "--sarif-tool", args.sarif_tool))
    elif args.operation == "test":
        inner = ["/usr/bin/python3", "-m", "unittest", "discover", "-s", "tests", "-v"]
    else:
        if args.evidence is not None:
            evidence = args.evidence.resolve()
            if evidence == runner or evidence.is_relative_to(runner) or runner.is_relative_to(evidence):
                raise ValueError("evidence must be disjoint from the read-only runner")
            _prepare_output_directory(evidence, uid, gid)
            command.extend(_mount(evidence, "/evidence", False))
        inner = args.command
        if inner and inner[0] == "--":
            inner = inner[1:]
        if not inner:
            raise ValueError("exec needs a command after --")
    return command + [args.image] + inner


def main(argv=None):
    arguments = parser().parse_args(argv)
    if shutil.which("docker") is None:
        print("Docker CLI is unavailable; install Docker and start its engine. No host fallback.", file=sys.stderr)
        return 2
    try:
        command = docker_command(arguments)
        return subprocess.run(command, check=False).returncode
    except (OSError, ValueError, KeyError) as exc:
        print(f"container launch failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
