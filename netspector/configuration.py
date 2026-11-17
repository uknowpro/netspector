"""Bounded configuration candidates; no runtime environment or template execution."""
from __future__ import annotations

import configparser
import ipaddress
import re
from dataclasses import dataclass, field
from xml.parsers import expat

URL = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*://')
VARIABLE = re.compile(r'\$\{([A-Za-z_][\w.-]*)\}')


@dataclass
class Entry:
    value: str
    file: str
    line: int | None
    reference: str

    def evidence(self):
        return dict(file=self.file, line=self.line, reference=self.reference)


def flatten(value, prefix='', active=None):
    active = set() if active is None else active
    if isinstance(value, (dict, list)):
        if id(value) in active:
            raise ValueError('Recursive configuration')
        active.add(id(value))
        items = value.items() if isinstance(value, dict) else enumerate(value)
        for key, child in items:
            path = f'{prefix}.{key}'.strip('.') if isinstance(value, dict) else f'{prefix}[{key}]'
            yield from flatten(child, path, active)
        active.remove(id(value))
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        yield prefix, str(value), None


def ini_entries(source):
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    try:
        parser.read_string(source)
    except configparser.Error as exc:
        raise ValueError('Invalid INI') from exc
    locations, section = {}, 'DEFAULT'
    for line, text in enumerate(source.splitlines(), 1):
        match = re.match(r'\s*\[([^]]+)\]', text)
        if match:
            section = match[1]
        elif text.strip() and not text.lstrip().startswith(('#', ';')):
            match = re.match(r'\s*([^=:]+?)\s*[=:]', text)
            if match:
                locations.setdefault((section, match[1].strip()), line)
    for section in ['DEFAULT', *parser.sections()]:
        values = parser.defaults() if section == 'DEFAULT' else parser[section]
        for key, value in values.items():
            origin = section if (section, key) in locations else 'DEFAULT'
            yield f'{section}.{key}', value, locations.get((origin, key))


@dataclass
class Node:
    tag: str
    attrs: dict
    line: int
    children: list = field(default_factory=list)
    text: str = ''


def xml_entries(source):
    """Reject DTDs/entities before expansion, including UTF-encoded declarations."""
    parser = expat.ParserCreate(namespace_separator='}')
    stack, roots = [], []
    count = 0

    def reject(*args):
        raise ValueError('XML DTD/entities are unsupported')

    def start(tag, attrs):
        nonlocal count
        count += 1
        if len(stack) >= 64 or count > 50000:
            raise ValueError('XML structural limit')
        node = Node(tag.split('}')[-1], attrs, parser.CurrentLineNumber)
        (stack[-1].children if stack else roots).append(node)
        stack.append(node)

    def characters(text):
        if stack:
            stack[-1].text += text

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda tag: stack.pop()
    parser.CharacterDataHandler = characters
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(source, True)
    except expat.ExpatError as exc:
        raise ValueError('Invalid XML') from exc
    entries, routes = [], []

    def visit(node, path):
        # Spring properties/map entries retain explicit configuration names.
        name = node.attrs.get('name') if node.tag == 'property' else node.attrs.get('key') if node.tag in {'entry', 'prop'} else None
        if name:
            value = node.attrs.get('value', node.text.strip())
            child = next((c for c in node.children if c.tag == 'value'), None)
            if child is not None:
                value = child.text.strip()
            entries.append((f'{path.rsplit(".", 1)[0]}.{name}', value, node.line))
            return
        children = {c.tag: c for c in node.children}
        if node.tag in {'context-param', 'init-param'} and {'param-name', 'param-value'} <= children.keys():
            entries.append((children['param-name'].text.strip(), children['param-value'].text.strip(), children['param-value'].line))
            return
        if node.tag == 'servlet-mapping':
            servlet = children.get('servlet-name')
            for child in node.children:
                if child.tag == 'url-pattern':
                    routes.append((child.text.strip(), child.line, servlet.text.strip() if servlet else path))
            return
        if not node.children and node.text.strip():
            entries.append((path, node.text.strip(), node.line))
        for attr, value in node.attrs.items():
            if attr.split('}')[-1] not in {'schemaLocation', 'noNamespaceSchemaLocation'} and attr not in {'id', 'name', 'key'}:
                entries.append((f'{path}.{attr.split("}")[-1]}', value, node.line))
        totals = {}
        for child in node.children:
            totals[child.tag] = totals.get(child.tag, 0) + 1
        seen = {}
        for child in node.children:
            seen[child.tag] = seen.get(child.tag, 0) + 1
            suffix = f'[{seen[child.tag]}]' if totals[child.tag] > 1 and child.tag != 'property' else ''
            visit(child, f'{path}.{child.tag}{suffix}')

    for root in roots:
        visit(root, root.tag)
    return entries, routes


class Configurations:
    def __init__(self):
        self.units = []

    def add(self, entries, file, export=None):
        values = {}
        for key, value, line in entries:
            # Ambiguous repeated keys are never silently selected.
            if key in values:
                values[key] = None
            else:
                values[key] = Entry(str(value), file, line, key)
        self.units.append((values, export))

    def build(self, emit, environment):
        diagnostics = []
        for local, export in self.units:
            budget = [0]
            limited = [False]

            def resolve(key, external, trail=()):
                budget[0] += 1
                if budget[0] > 2048:
                    limited[0] = True
                    return None
                if len(trail) >= 16 or key in trail:
                    return None
                entry = local.get(key) if key in local else external.get(key)
                if entry is None:
                    return None
                if len(entry.value) > 8192:
                    limited[0] = True
                    return None
                evidence = [entry.evidence()]
                failed = False
                expanded_size = 0

                def replace(match):
                    nonlocal failed, expanded_size
                    if failed:
                        return ""
                    reference = match[1]
                    scoped = key.rsplit('.', 1)[0] + '.' + reference if '.' in key else reference
                    if reference not in local and reference not in external and (scoped in local or scoped in external):
                        reference = scoped
                    result = resolve(reference, external, (*trail, key))
                    if result is None:
                        failed = True
                        return ''
                    value, proof = result
                    expanded_size += len(value)
                    if expanded_size > 8192:
                        failed = True
                        limited[0] = True
                        return ""
                    evidence.extend(proof)
                    return value

                value = VARIABLE.sub(replace, entry.value)
                if len(value) > 8192:
                    limited[0] = True
                if failed or len(value) > 8192 or any(t in value for t in ('${', '$(', '{{')):
                    return None
                return value, evidence

            # Every candidate uses at most one other file/document: no profile mixing.
            contexts = [{}]
            names = set()
            pending = [e.value for e in local.values() if e is not None]
            while pending and len(names) < 256:
                for name in VARIABLE.findall(pending.pop()):
                    if name not in names:
                        names.add(name)
                        pending.extend(e.value for unit, _ in self.units for k, e in unit.items() if k == name and e is not None)
            # Include all direct references (a template may contain host and port).
            names.update(n for e in local.values() if e for n in VARIABLE.findall(e.value))
            contexts.extend(unit for unit, _ in self.units if unit is not local and names.intersection(unit))
            if len(contexts) > 65:
                file = next((e.file for e in local.values() if e), '')
                diagnostics.append(dict(file=file, message='Configuration candidate limit exceeded'))
                contexts = contexts[:65]

            def proofs(items):
                return [dict(t) for t in dict.fromkeys(tuple(e.items()) for e in items)]

            for key, entry in local.items():
                if entry is None:
                    continue
                emitted = set()
                for external in contexts:
                    budget[0] = 0
                    result = resolve(key, external)
                    if result is None or not URL.match(result[0]) or environment.safe_target(result[0]) == '<invalid-url>':
                        continue
                    value, evidence = result
                    evidence = proofs(evidence)
                    identity = (environment.safe_target(value), str(evidence))
                    if identity in emitted:
                        continue
                    emitted.add(identity)
                    expanded = value != entry.value
                    emit(entry.file, entry.line, 'unknown', 'configuration', value, 'candidate', reference=key, evidence=evidence if expanded else [])
                    if export is not None:
                        environment.add(export + key, value, entry.file, entry.line, reference=key, **({'evidence': evidence} if expanded else {}))
                if not emitted and ('${' in entry.value or '{{' in entry.value) and (URL.match(entry.value) or re.search(r'(?:^|[._-])(url|uri|endpoint)$', key, re.I)):
                    emit(entry.file, entry.line, 'unknown', 'configuration', '<dynamic>', 'unresolved', reference=key, evidence=[entry.evidence()])

            groups = {}
            for key in local:
                match = re.fullmatch(r'(?:(.*)[._])?(host|hostname|port|protocol|scheme|path)', key, re.I)
                if match:
                    group, component = match.groups()
                    group = group or ''
                    groups.setdefault(group, {})[component.lower()] = key
            for group, parts in groups.items():
                host_key = parts.get('host', parts.get('hostname'))
                if not host_key or 'port' not in parts:
                    continue
                entry = local[host_key]
                if entry is None:
                    continue
                found = set()
                for external in contexts:
                    values, evidence = {}, []
                    for component, key in parts.items():
                        budget[0] = 0
                        result = resolve(key, external)
                        if result is None:
                            break
                        values[component] = result[0]
                        evidence.extend(result[1])
                    else:
                        host = values.get('host', values.get('hostname', ''))
                        port = values['port']
                        scheme = values.get('protocol', values.get('scheme'))
                        path = values.get('path', '')
                        if not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]+', host) or not re.fullmatch(r'\d{1,5}', port) or not 1 <= int(port) <= 65535:
                            continue
                        if scheme and not re.fullmatch(r'[A-Za-z][A-Za-z0-9+.-]*', scheme):
                            continue
                        if ':' in host or '[' in host or ']' in host:
                            try:
                                ipaddress.IPv6Address(host.strip('[]'))
                            except ValueError:
                                continue
                            host = f'[{host.strip(chr(91) + chr(93))}]'
                        if path and not path.startswith('/'):
                            continue
                        target = f'{host}:{int(port)}'
                        if scheme:
                            target = f'{scheme}://{target}{path}'
                        evidence = proofs(evidence)
                        identity = (target, str(evidence))
                        if identity not in found:
                            found.add(identity)
                            emit(entry.file, entry.line, 'unknown', 'configuration-endpoint', target, 'candidate', port=int(port), reference=group or 'endpoint', evidence=evidence)
                if not found:
                    emit(entry.file, entry.line, 'unknown', 'configuration-endpoint', '<dynamic>', 'unresolved', reference=group or 'endpoint', evidence=[local[k].evidence() for k in parts.values() if local[k]])
            if limited[0]:
                file = next((e.file for e in local.values() if e), "")
                diagnostics.append(dict(file=file, message="Configuration expansion limit exceeded"))
        return diagnostics
