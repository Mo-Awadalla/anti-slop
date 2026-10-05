"""Optional Git touch counts; ranking never changes diagnostic severity."""

from __future__ import annotations

import copy
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .sarif import safe_relative_path
from .schema import SchemaError


def _git(repo: Path, *args: str) -> str:
    process = subprocess.run(['git', '--literal-pathspecs', '-C', str(repo), *args], capture_output=True, timeout=30, check=False)
    if process.returncode:
        raise RuntimeError('Git history unavailable')
    return process.stdout.decode('utf-8', errors='strict').strip()


def rank_hotspots(document: dict | list, repo: str | Path, *, lookback_days: int, revision: str = 'HEAD') -> dict:
    if type(lookback_days) is not int or lookback_days < 1:
        raise SchemaError('lookback-days must be a positive integer')
    if not isinstance(revision, str) or not revision or revision.startswith('-'):
        raise SchemaError('revision must identify a Git commit')
    root = Path(repo).resolve()
    result = copy.deepcopy(document) if isinstance(document, dict) else {'kind': 'ranked-findings', 'schema_version': 1, 'findings': copy.deepcopy(document)}
    items = result['signals'] if result.get('kind') == 'tool-signals' else result['findings']
    limitations = []
    history = {'lookback_days': lookback_days, 'requested_revision': revision, 'revision': None,
               'window_start': None, 'window_end': None, 'limitations': limitations}
    try:
        commit = _git(root, 'rev-parse', '--verify', '--end-of-options', revision + '^{commit}')
        timestamp = int(_git(root, 'show', '-s', '--format=%ct', commit))
        end = datetime.fromtimestamp(timestamp, timezone.utc)
        start = end - timedelta(days=lookback_days)
        history.update(revision=commit, window_start=start.isoformat(), window_end=end.isoformat())
        if _git(root, 'rev-parse', '--is-shallow-repository') == 'true':
            limitations.append('shallow-history: counts cover only available commits in the requested window')
        limitations.append('touch-counts: no rename following; only paths present in each signal/finding are queried')
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, OverflowError):
        history.update(revision=None, window_start=None, window_end=None)
        limitations.append('history-unavailable: no churn count or history-based ranking is asserted')
    counts = {}
    for item in items:
        paths = tuple(sorted({location['path'] for location in item['locations']})) if 'locations' in item else ((item['path'],) if item.get('path') else ())
        for path in paths:
            safe_relative_path(path, root)
        count = None
        if history['revision'] is not None and paths:
            if paths not in counts:
                try:
                    log = _git(root, 'log', '--full-history', '--format=%H', '--no-renames', '--since-as-filter=' + history['window_start'], '--until=' + history['window_end'], history['revision'], '--', *paths)
                    counts[paths] = len(set(log.splitlines())) if log else 0
                except (OSError, RuntimeError, UnicodeError, subprocess.TimeoutExpired):
                    counts[paths] = None
                    if 'path-history-unavailable: one or more touch counts could not be collected' not in limitations:
                        limitations.append('path-history-unavailable: one or more touch counts could not be collected')
            count = counts[paths]
        item['churn'] = {'commits': count, 'paths': list(paths)}
    # Python's stable sort preserves input order for equal or unavailable counts.
    items.sort(key=lambda item: (item['churn']['commits'] is None, -(item['churn']['commits'] or 0)))
    result['history'] = history
    return result
