"""SARIF tool observations, deliberately separate from adjudicated Findings."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

from .schema import SchemaError

SARIF_SCHEMA = 'https://json.schemastore.org/sarif-2.1.0.json'
LEVELS = {'none', 'note', 'warning', 'error'}


def decode_json(text: str | bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise SchemaError(f'duplicate JSON key: {key}')
            result[key] = value
        return result

    def constant(value):
        raise SchemaError(f'invalid JSON constant: {value}')

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f'invalid JSON: {exc}') from exc


def _object(value, label):
    if not isinstance(value, dict):
        raise SchemaError(f'{label} must be an object')
    return value


def _array(value, label):
    if not isinstance(value, list):
        raise SchemaError(f'{label} must be an array')
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f'{label} must be nonempty text')
    return value


def _index(value, values, label):
    if type(value) is not int or value < 0 or value >= len(values):
        raise SchemaError(f'{label} is out of bounds')
    return values[value]


def safe_relative_path(path: str, repo: Path | None = None) -> str:
    _text(path, 'path')
    if path.startswith('/') or '\\' in path or any(ord(c) < 32 for c in path):
        raise SchemaError('path must be safe and repository-relative')
    if any(part in ('', '.', '..') for part in path.split('/')) or ':' in path.split('/')[0]:
        raise SchemaError('path contains traversal or an absolute URI')
    if repo is not None:
        try:
            (repo / path).resolve().relative_to(repo.resolve())
        except ValueError as exc:
            raise SchemaError('path escapes repository through a symlink') from exc
    return path


class _Locations:
    def __init__(self, run: dict, repo: Path, *, recorded_workspace: bool = False):
        self.repo = repo.resolve()
        self.root_uri = self.repo.as_uri() + '/'
        self.recorded_workspace = recorded_workspace
        self.artifacts = _array(run.get('artifacts', []), 'artifacts')
        self.bases = _object(run.get('originalUriBaseIds', {}), 'originalUriBaseIds')

    def uri(self, location: dict, visiting=()):
        location = _object(location, 'artifactLocation')
        if 'index' in location and location['index'] != -1:
            artifact = _object(_index(location['index'], self.artifacts, 'artifact index'), 'artifact')
            indexed = _object(artifact.get('location'), 'artifact.location')
            merged = dict(indexed)
            merged.update({key: value for key, value in location.items() if key != 'index'})
            location = merged
        uri = _text(location.get('uri'), 'artifactLocation.uri')
        if re.search(r'%(?![0-9a-fA-F]{2})', uri):
            raise SchemaError('URI contains malformed percent encoding')
        parsed = urlsplit(uri)
        decoded_path = unquote(parsed.path, errors='strict')
        if parsed.scheme not in ('', 'file') or parsed.netloc not in ('', 'localhost') or parsed.query or parsed.fragment:
            raise SchemaError('only local repository file URIs are supported')
        if '\\' in decoded_path or any(ord(c) < 32 for c in decoded_path) or '..' in decoded_path.split('/'):
            raise SchemaError('URI contains traversal or unsafe characters')
        if self.recorded_workspace and (decoded_path == '/workspace' or decoded_path.startswith('/workspace/')):
            # Only verified sandbox captures may use the runner's mount root.
            # Decode before matching, but retain the traversal/authority checks
            # above and repository/symlink checks below for the translated URI.
            uri = self.repo.as_uri() + quote(decoded_path[len('/workspace'):], safe='/')
        base_id = location.get('uriBaseId')
        base = self.root_uri
        if base_id is not None:
            _text(base_id, 'uriBaseId')
            if base_id in visiting or base_id not in self.bases:
                raise SchemaError('unknown or cyclic uriBaseId')
            base = self.uri(self.bases[base_id], visiting + (base_id,))
        absolute = urljoin(base, uri)
        parsed_absolute = urlsplit(absolute)
        target = Path(unquote(parsed_absolute.path, errors='strict'))
        try:
            target.resolve().relative_to(self.repo)
        except ValueError as exc:
            raise SchemaError('SARIF URI escapes repository') from exc
        return absolute

    def normalize(self, value):
        location = _object(value, 'location')
        if 'physicalLocation' not in location:
            return None  # Logical-only locations cannot provide a physical path.
        physical = _object(location['physicalLocation'], 'physicalLocation')
        uri = self.uri(physical.get('artifactLocation'))
        path = Path(unquote(urlsplit(uri).path)).resolve().relative_to(self.repo).as_posix()
        result = {'path': safe_relative_path(path, self.repo)}
        region = _object(physical.get('region', {}), 'region')
        for sarif_name, name in (('startLine', 'line'), ('startColumn', 'column'), ('endLine', 'end_line'), ('endColumn', 'end_column')):
            if sarif_name in region:
                number = region[sarif_name]
                if type(number) is not int or number < 1:
                    raise SchemaError(f'{sarif_name} must be a positive integer')
                result[name] = number
        if 'column' in result and 'line' not in result:
            raise SchemaError('startColumn requires startLine')
        if result.get('end_line', result.get('line', 1)) < result.get('line', 1):
            raise SchemaError('region ends before it starts')
        if result.get('end_line', result.get('line')) == result.get('line') and result.get('end_column', result.get('column', 1)) < result.get('column', 1):
            raise SchemaError('region ends before it starts')
        return result


def _rule(result, driver, extensions):
    reference = _object(result.get('rule', {}), 'rule reference')
    component = driver
    component_ref = reference.get('toolComponent')
    if component_ref is not None:
        component_ref = _object(component_ref, 'toolComponent')
        if 'index' in component_ref:
            component = _object(_index(component_ref['index'], extensions, 'toolComponent index'), 'extension')
        elif 'name' in component_ref:
            matches = [tool for tool in [driver] + extensions if tool.get('name') == component_ref['name']]
            if len(matches) != 1:
                raise SchemaError('toolComponent name is unknown or ambiguous')
            component = matches[0]
        else:
            raise SchemaError('toolComponent requires name or index')
    rules = _array(component.get('rules', []), 'rules')
    rule_id = result.get('ruleId', reference.get('id'))
    if 'ruleId' in result and 'id' in reference and result['ruleId'] != reference['id']:
        raise SchemaError('rule reference IDs disagree')
    index = result.get('ruleIndex', reference.get('index'))
    if 'ruleIndex' in result and 'index' in reference and result['ruleIndex'] != reference['index']:
        raise SchemaError('rule reference indices disagree')
    if ('ruleIndex' in result or 'index' in reference) and (type(index) is not int or index < -1):
        raise SchemaError('rule index must be an integer >= -1')
    if index == -1:
        index = None  # SARIF's explicit unknown-index sentinel.
    rule = {}
    if index is not None:
        rule = _object(_index(index, rules, 'rule index'), 'rule')
        if rule_id is not None and rule_id != rule.get('id'):
            raise SchemaError('rule ID disagrees with rule index')
        rule_id = _text(rule.get('id'), 'indexed rule ID')
    elif rule_id is not None:
        matches = [item for item in rules if _object(item, 'rule').get('id') == rule_id]
        if len(matches) > 1:
            raise SchemaError('duplicate rule ID')
        rule = matches[0] if matches else {}
    # SARIF permits results without a rule. Do not invent an identifier.
    normalized = {}
    if rule_id is not None:
        normalized['id'] = _text(rule_id, 'rule ID')
    if 'name' in rule:
        normalized['name'] = _text(rule['name'], 'rule name')
    tool = {'name': _text(component.get('name'), 'tool name')}
    if 'version' in component:
        tool['version'] = _text(component['version'], 'tool version')
    return tool, normalized, rule, component


def _message(value, rule, component):
    message = _object(value, 'message')
    text = message.get('text', message.get('markdown'))
    if text is None and 'id' in message:
        identifier = _text(message['id'], 'message ID')
        templates = _object(rule.get('messageStrings', {}), 'messageStrings')
        template = templates.get(identifier)
        if template is None:
            template = _object(component.get('globalMessageStrings', {}), 'globalMessageStrings').get(identifier)
        template = _object(template, 'message template')
        text = template.get('text', template.get('markdown'))
    text = _text(text, 'message text')
    arguments = _array(message.get('arguments', []), 'message arguments')
    if any(not isinstance(argument, str) for argument in arguments):
        raise SchemaError('message arguments must be strings')
    if arguments:
        def substitute(match):
            number = int(match.group(1))
            if number >= len(arguments):
                raise SchemaError('message argument index is out of bounds')
            return arguments[number]
        text = re.sub(r'\{(\d+)\}', substitute, text)
    return text


def import_sarif(text: str | bytes, repo: str | Path, *, capture: dict | None = None,
                 recorded_workspace: bool = False) -> dict:
    """Import observations; callers must verify sandbox evidence before allowing /workspace."""
    document = _object(decode_json(text), 'SARIF')
    if document.get('version') != '2.1.0':
        raise SchemaError('SARIF version must be 2.1.0')
    signals = []
    for run_index, run_value in enumerate(_array(document.get('runs'), 'runs')):
        run = _object(run_value, 'run')
        tool = _object(run.get('tool'), 'tool')
        driver = _object(tool.get('driver'), 'driver')
        _text(driver.get('name'), 'driver name')
        extensions = [_object(value, 'extension') for value in _array(tool.get('extensions', []), 'extensions')]
        locations = _Locations(run, Path(repo), recorded_workspace=recorded_workspace)
        for result_index, value in enumerate(_array(run.get('results', []), 'results')):
            result = _object(value, 'result')
            tool_identity, rule_identity, rule, component = _rule(result, driver, extensions)
            level = result.get('level', _object(rule.get('defaultConfiguration', {}), 'defaultConfiguration').get('level', 'warning'))
            if not isinstance(level, str) or level not in LEVELS:
                raise SchemaError('invalid SARIF level')
            normalized_locations = []
            omitted = 0
            for location in _array(result.get('locations', []), 'locations'):
                normalized = locations.normalize(location)
                if normalized is None:
                    omitted += 1
                else:
                    normalized_locations.append(normalized)
            signal = {'id': f'sarif-{run_index + 1}-{result_index + 1}', 'tool': tool_identity,
                      'rule': rule_identity, 'level': level, 'message': _message(result.get('message'), rule, component),
                      'locations': normalized_locations}
            if omitted:
                signal['omitted_logical_locations'] = omitted
            properties = _object(result.get('properties', {}), 'properties')
            if 'antiSlopPriority' in properties:
                signal['priority'] = properties['antiSlopPriority']
            signals.append(signal)
    return load_signals({'schema_version': 1, 'kind': 'tool-signals', 'capture': capture or {'kind': 'external'}, 'signals': signals})


def load_signals(value) -> dict:
    document = _object(decode_json(value) if isinstance(value, (str, bytes)) else value, 'signals')
    if type(document.get('schema_version')) is not int or document.get('schema_version') != 1 or document.get('kind') != 'tool-signals':
        raise SchemaError('expected tool-signals schema_version 1')
    _object(document.get('capture'), 'capture')
    seen = set()
    for signal in _array(document.get('signals'), 'signals'):
        signal = _object(signal, 'signal')
        identifier = _text(signal.get('id'), 'signal ID')
        if identifier in seen:
            raise SchemaError('duplicate signal ID')
        seen.add(identifier)
        tool = _object(signal.get('tool'), 'signal tool')
        _text(tool.get('name'), 'signal tool name')
        if 'version' in tool:
            _text(tool['version'], 'signal tool version')
        rule = _object(signal.get('rule'), 'signal rule')
        for key in ('id', 'name'):
            if key in rule:
                _text(rule[key], f'rule {key}')
        if not isinstance(signal.get('level'), str) or signal['level'] not in LEVELS:
            raise SchemaError('invalid signal level')
        _text(signal.get('message'), 'signal message')
        if 'priority' in signal:
            priority = signal['priority']
            if not (type(priority) is int or (type(priority) is float and math.isfinite(priority)) or (isinstance(priority, str) and priority.strip())):
                raise SchemaError('optional priority must be finite numeric or nonempty text metadata')
        for location in _array(signal.get('locations'), 'signal locations'):
            location = _object(location, 'signal location')
            safe_relative_path(location.get('path'))
            for key in ('line', 'column', 'end_line', 'end_column'):
                if key in location and (type(location[key]) is not int or location[key] < 1):
                    raise SchemaError('location coordinates must be positive integers')
            if 'column' in location and 'line' not in location:
                raise SchemaError('column requires line')
            if location.get('end_line', location.get('line', 1)) < location.get('line', 1):
                raise SchemaError('location ends before it starts')
            if location.get('end_line', location.get('line')) == location.get('line') and location.get('end_column', location.get('column', 1)) < location.get('column', 1):
                raise SchemaError('location ends before it starts')
    return document


def export_sarif(value, *, tool_name: str | None = None) -> dict:
    document = load_signals(value)
    groups = {}
    for signal in document['signals']:
        if tool_name is not None and signal['tool']['name'] != tool_name:
            continue
        key = (signal['tool']['name'], signal['tool'].get('version'))
        groups.setdefault(key, []).append(signal)
    if tool_name is not None and not groups:
        raise SchemaError(f'no signals for tool: {tool_name}')
    runs = []
    for (name, version), signals in groups.items():
        driver = {'name': name}
        if version is not None:
            driver['version'] = version
        rules = {}
        results = []
        for signal in signals:
            result = {'level': signal['level'], 'message': {'text': signal['message']}, 'locations': [],
                      'properties': {'antiSlopSignalId': signal['id'], 'antiSlopObservation': 'tool-signal; requires contextual adjudication'}}
            if 'id' in signal['rule']:
                rule_id = signal['rule']['id']
                result['ruleId'] = rule_id
                if rule_id not in rules:
                    rules[rule_id] = dict(signal['rule'])
            for location in signal['locations']:
                physical = {'artifactLocation': {'uri': quote(location['path'], safe='/')}}
                region = {sarif_name: location[key] for key, sarif_name in (('line', 'startLine'), ('column', 'startColumn'), ('end_line', 'endLine'), ('end_column', 'endColumn')) if key in location}
                if region:
                    physical['region'] = region
                result['locations'].append({'physicalLocation': physical})
            if 'priority' in signal:
                result['properties']['antiSlopPriority'] = signal['priority']
            if 'churn' in signal:
                result['properties']['antiSlopChurn'] = signal['churn']
            results.append(result)
        if rules:
            driver['rules'] = list(rules.values())
        runs.append({'tool': {'driver': driver}, 'results': results})
    return {'$schema': SARIF_SCHEMA, 'version': '2.1.0', 'runs': runs}
