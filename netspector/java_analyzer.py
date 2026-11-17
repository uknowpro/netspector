"""Dependency-free, bounded Java lexical/structural analysis (not a compiler).

Only explicitly imported Spring controllers and recognized client types are used.
Comments and literals are tokenized, scopes are kept separate, and unknown values
remain unresolved. No target Java code, build tool, or classloader is executed.
"""
from dataclasses import dataclass
import re


SPRING = 'org.springframework.web.bind.annotation.'
MAPPINGS = {'RequestMapping', 'GetMapping', 'PostMapping', 'PutMapping', 'PatchMapping', 'DeleteMapping'}
CONTROLLERS = {SPRING + 'RestController', 'org.springframework.stereotype.Controller'}
REST = 'org.springframework.web.client.RestTemplate'
REQUEST = 'java.net.http.HttpRequest'
URI = 'java.net.URI'
VALUE = 'org.springframework.beans.factory.annotation.Value'
REST_METHODS = {'getForObject', 'getForEntity', 'postForObject', 'postForEntity', 'postForLocation',
                'put', 'delete', 'patchForObject', 'headForHeaders', 'optionsForAllow', 'exchange', 'execute'}
KNOWN = CONTROLLERS | {SPRING + name for name in MAPPINGS} | {REST, REQUEST, URI, VALUE, REQUEST + '.Builder'}
TOKEN = re.compile(r'(?P<space>\s+)|(?P<comment>//[^\n]*|/\*[\s\S]*?\*/)|'
                   r'(?P<text>"""[\s\S]*?(?<!\\)""")|'
                   r'(?P<string>"(?:\\[^\r\n]|[^"\\\r\n])*")|'
                   r"(?P<char>'(?:\\[^\r\n]|[^'\\\r\n])*')|"
                   r'(?P<id>[A-Za-z_$][\w$]*)|(?P<number>\d+)|'
                   r'(?P<symbol>\+=|-=|\+\+|--|==|!=|<=|>=|->|&&|\|\||[^\s])')


@dataclass(frozen=True)
class Token:
    text: str
    kind: str
    line: int
    index: int


def tokenize(source):
    result, line, position = [], 1, 0
    for match in TOKEN.finditer(source):
        value, kind = match.group(), match.lastgroup
        if match.start() != position:
            raise SyntaxError('Invalid Java token')
        if kind == 'symbol' and (value in {'"', "'", '\\'} or source[match.start():match.start()+2] == '/*'):
            raise SyntaxError('Unsupported or unterminated Java literal')
        if kind not in {'space', 'comment'}:
            result.append(Token(value, kind, line, len(result)))
        line += value.count('\n')
        position = match.end()
    if len(result) > 200_000:
        raise ValueError('Java token limit exceeded')
    return result


def literal(token):
    if token.kind != 'string':
        return None
    value = token.text[1:-1]
    simple = {'b': '\b', 't': '\t', 'n': '\n', 'f': '\f', 'r': '\r', 's': ' ', '"': '"', "'": "'", '\\': '\\'}
    def decode(match):
        escape = match.group()[1:]
        if escape.startswith('u'):
            return chr(int(escape.lstrip('u'), 16))
        if escape[0].isdigit():
            return chr(int(escape, 8))
        if escape not in simple:
            raise ValueError('Unsupported Java string escape')
        return simple[escape]
    decoded = re.sub(r'\\(?:u+[0-9a-fA-F]{4}|[0-3][0-7]{0,2}|[4-7][0-7]?|.)', decode, value)
    return decoded.encode('utf-16', 'surrogatepass').decode('utf-16')


def split(tokens, separator=','):
    parts, current, depth = [], [], 0
    for token in tokens:
        if token.text in {'(', '[', '{'}:
            depth += 1
        elif token.text in {')', ']', '}'}:
            depth -= 1
        if token.text == separator and depth == 0:
            parts.append(current)
            current = []
        else:
            current.append(token)
    if current:
        parts.append(current)
    return parts


def spelling(tokens):
    return ''.join(t.text for t in tokens)


class Java:
    def __init__(self, source, file, emit, safe_target):
        self.tokens = tokenize(source)
        self.file, self.emit, self.safe_target = file, emit, safe_target
        self.pairs, stack = {}, []
        for token in self.tokens:
            if token.text in {'(', '{', '['}:
                stack.append(token)
            elif token.text in {')', '}', ']'}:
                if not stack or {'(': ')', '{': '}', '[': ']'}[stack[-1].text] != token.text:
                    raise SyntaxError('Unbalanced Java delimiters')
                first = stack.pop()
                self.pairs[first.index] = token.index
                self.pairs[token.index] = first.index
        if stack:
            raise SyntaxError('Unbalanced Java delimiters')
        self.imports, self.wildcards = {}, set()
        for i, token in enumerate(self.tokens):
            if token.text == 'import':
                end = self.until(i + 1, ';')
                name = spelling(self.tokens[i+1:end])
                if name.startswith('static'):
                    continue
                if name.endswith('.*'):
                    self.wildcards.add(name[:-2])
                else:
                    self.imports[name.split('.')[-1]] = name
        self.class_names = {self.tokens[i+1].text for i, t in enumerate(self.tokens[:-1])
                            if t.text in {'class', 'interface', 'record', 'enum'} and self.tokens[i+1].kind == 'id'}

    def until(self, start, end):
        while start < len(self.tokens) and self.tokens[start].text != end:
            start += 1
        return start

    def qualify(self, name):
        if name in KNOWN or name in {'java.lang.String', 'java.lang.System'}:
            return name
        first, _, suffix = name.partition('.')
        if first in self.class_names:
            return name
        if first in self.imports:
            return self.imports[first] + ('.' + suffix if suffix else '')
        if first in {'String', 'System'}:
            return 'java.lang.' + name
        matches = [full for full in KNOWN if full.endswith('.' + name) and full[:-len(name)-1] in self.wildcards]
        return matches[0] if len(matches) == 1 else name

    def annotation(self, index):
        start = index
        index += 1
        names = []
        while index < len(self.tokens) and (self.tokens[index].kind == 'id' or self.tokens[index].text == '.'):
            names.append(self.tokens[index])
            index += 1
            if index >= len(self.tokens) or self.tokens[index].text != '.':
                break
            names.append(self.tokens[index])
            index += 1
        args = []
        if index < len(self.tokens) and self.tokens[index].text == '(':
            end = self.pairs[index]
            args = self.tokens[index+1:end]
            index = end + 1
        return dict(name=self.qualify(spelling(names)), args=args, line=self.tokens[start].line), index

    def members(self, start, end):
        index = start
        while index < end:
            if self.tokens[index].text == ';':
                index += 1
                continue
            annotations = []
            while index < end and self.tokens[index].text == '@':
                annotation, index = self.annotation(index)
                annotations.append(annotation)
            begin = index
            while index < end and self.tokens[index].text not in {';', '{'}:
                if self.tokens[index].text in {'(', '['}:
                    index = self.pairs[index] + 1
                else:
                    index += 1
            if index >= end:
                break
            header = self.tokens[begin:index]
            if self.tokens[index].text == '{':
                close = self.pairs[index]
                yield annotations, header, (index + 1, close)
                index = close + 1
            else:
                yield annotations, header, None
                index += 1

    def proof(self, line, reference):
        return dict(file=self.file, line=line, reference=reference)

    def declaration(self, tokens, annotations=()):
        # Scalar declarations only; comma-separated declarations and generic types
        # are intentionally not propagated.
        if not tokens or any(t.text == ',' for t in tokens):
            return None
        eq = next((i for i, t in enumerate(tokens) if t.text == '='), len(tokens))
        left = tokens[:eq]
        if len(left) < 2 or left[-1].kind != 'id' or any(t.text in {'(', ')', '<', '>', '[', ']'} for t in left):
            return None
        modifiers = {'public', 'private', 'protected', 'static', 'final', 'volatile', 'transient'}
        type_tokens = [t for t in left[:-1] if t.text not in modifiers]
        typename = self.qualify(spelling(type_tokens))
        if not type_tokens or any(t.kind != 'id' and t.text != '.' for t in type_tokens):
            return None
        ref = None
        for annotation in annotations:
            if annotation['name'] == VALUE and len(annotation['args']) == 1:
                content = literal(annotation['args'][0])
                match = re.fullmatch(r'\$\{([A-Za-z0-9_.-]+)(?::[^{}]*)?\}', content or '')
                if match:
                    ref = 'property:' + match.group(1)
        return dict(name=left[-1].text, type=typename, expression=tokens[eq+1:] if eq < len(tokens) else [],
                    final=any(t.text == 'final' for t in left), reference=ref, line=left[-1].line, index=left[-1].index)

    def value(self, tokens, bindings, class_name, seen=()):
        if not tokens:
            return '<dynamic>', None, []
        if tokens[0].text == '(' and self.pairs.get(tokens[0].index) == tokens[-1].index:
            return self.value(tokens[1:-1], bindings, class_name, seen)
        chunks = split(tokens, '+')
        if len(chunks) > 1:
            values = [self.value(chunk, bindings, class_name, seen) for chunk in chunks]
            if all(v[0] != '<dynamic>' and not v[1] for v in values):
                return ''.join(v[0] for v in values), None, [proof for v in values for proof in v[2]]
            return '<dynamic>', None, []
        if len(tokens) == 1 and tokens[0].kind == 'string':
            result = literal(tokens[0])
            if '${' in result or '#{' in result:
                return '<dynamic>', None, []
            return result, None, []
        name = spelling(tokens)
        if name.startswith('this.') or name.startswith(class_name + '.'):
            name = '@field:' + name.split('.', 1)[1]
        if name in bindings and name not in seen:
            binding = bindings[name]
            if binding and binding['safe'] and (binding['field'] or binding['index'] < tokens[0].index):
                proof = [self.proof(binding['line'], binding['name'])]
                if binding['reference']:
                    return '<dynamic>', binding['reference'], proof
                target, ref, evidence = self.value(binding['expression'], bindings, class_name, seen + (name,))
                return target, ref, evidence + proof
            return '<dynamic>', None, []
        opening = next((i for i, t in enumerate(tokens) if t.text == '('), None)
        if opening is not None and self.pairs.get(tokens[opening].index) == tokens[-1].index:
            prefix = spelling(tokens[:opening])
            args = split(tokens[opening+1:-1])
            if len(args) == 1:
                owner, _, method = prefix.rpartition('.')
                if self.qualify(owner) == 'java.lang.System' and method == 'getenv' and owner not in bindings:
                    key, _, _ = self.value(args[0], bindings, class_name, seen)
                    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                        return '<dynamic>', 'env:' + key, []
                if ((self.qualify(owner) == URI and method == 'create' and owner not in bindings)
                        or (prefix.startswith('new') and self.qualify(prefix[3:]) == URI)):
                    return self.value(args[0], bindings, class_name, seen)
        return '<dynamic>', None, []

    def paths(self, annotation, bindings, class_name):
        expressions = []
        for arg in split(annotation['args']):
            if len(arg) > 1 and arg[1].text == '=':
                if arg[0].text not in {'value', 'path'}:
                    continue
                arg = arg[2:]
            if arg and arg[0].text == '{' and self.pairs.get(arg[0].index) == arg[-1].index:
                expressions.extend(split(arg[1:-1]))
            else:
                expressions.append(arg)
        if not expressions:
            return [('', None, [])]
        return [self.value(expr, bindings, class_name) for expr in expressions]

    def run(self):
        for annotations, header, body in self.members(0, len(self.tokens)):
            self.class_body(annotations, header, body)

    def class_body(self, annotations, header, body):
        kind_index = next((i for i, t in enumerate(header) if t.text in {'class', 'interface', 'record', 'enum'}), None)
        if body is None or kind_index is None or kind_index + 1 >= len(header):
            return
        class_name = header[kind_index+1].text
        members = list(self.members(*body))
        bindings = {}
        for anns, declaration, block in members:
            if block is None:
                binding = self.declaration(declaration, anns)
                if binding:
                    binding.update(safe=binding['final'] or bool(binding['reference']), field=True)
                    if binding['reference'] and any(t.text == binding['name'] and self.tokens[t.index+1].text in {'=', '+=', '-=', '++', '--'}
                                                    for t in self.tokens[body[0]:body[1]-1]):
                        binding['safe'] = False
                    bindings[binding['name']] = binding
                    bindings['@field:' + binding['name']] = binding
        controller = any(a['name'] in CONTROLLERS for a in annotations)
        class_mappings = [a for a in annotations if a['name'] == SPRING + 'RequestMapping']
        prefixes = self.paths(class_mappings[0], bindings, class_name) if len(class_mappings) == 1 else [('', None, [])]
        if len(class_mappings) > 1:
            prefixes = [('<dynamic>', None, [])]
        for anns, declaration, block in members:
            if any(t.text in {'class', 'interface', 'record', 'enum'} for t in declaration):
                self.class_body(anns, declaration, block)
                continue
            opening = next((i for i, t in enumerate(declaration) if t.text == '('), None)
            if opening is None or any(t.text == '=' for t in declaration[:opening]):
                continue
            if controller:
                mappings = [a for a in anns if a['name'] in {SPRING + name for name in MAPPINGS}]
                for annotation in mappings:
                    paths = self.paths(annotation, bindings, class_name)
                    if len(prefixes) * len(paths) > 256:
                        raise ValueError('Java route expansion limit exceeded')
                    for prefix, _, prefix_proof in prefixes:
                        for path, _, path_proof in paths:
                            target = '<dynamic>' if '<dynamic>' in {prefix, path} or len(mappings) > 1 else '/' + '/'.join(p.strip('/') for p in (prefix, path) if p.strip('/'))
                            proof = prefix_proof + path_proof + [self.proof(a['line'], a['name']) for a in class_mappings]
                            self.emit(self.file, annotation['line'], 'inbound', 'route', target,
                                      'unresolved' if target == '<dynamic>' else 'declared', protocol='http',
                                      reference='java:' + annotation['name'], evidence=proof)
            if block:
                self.calls(declaration, opening, block, bindings, class_name)

    def calls(self, header, opening, block, fields, class_name):
        bindings = dict(fields)
        close = self.pairs[header[opening].index]
        params = self.tokens[header[opening].index+1:close]
        for parameter in split(params):
            # Remove parameter annotations without confusing their argument lists.
            stripped, i = [], 0
            while i < len(parameter):
                if parameter[i].text == '@':
                    _, end = self.annotation(parameter[i].index)
                    while i < len(parameter) and parameter[i].index < end:
                        i += 1
                else:
                    stripped.append(parameter[i]); i += 1
            binding = self.declaration(stripped)
            if binding:
                binding.update(safe=False, field=False)
                bindings[binding['name']] = binding
            elif stripped:
                bindings[stripped[-1].text] = None
        # Recognize local scalar declarations. Bindings in nested blocks are blocked
        # for the whole method rather than incorrectly borrowing a field value.
        body = self.tokens[block[0]:block[1]]
        local, depth = {}, 0
        start = 0
        for index, token in enumerate(body):
            if token.text in {'{', '}'}:
                depth += 1 if token.text == '{' else -1
                start = index + 1
            elif token.text == ';':
                binding = self.declaration(body[start:index])
                if binding:
                    binding.update(safe=depth == 0, field=False)
                    name = binding['name']
                    local[name] = binding if name not in local else None
                start = index + 1
        for name, binding in local.items():
            writes = sum(t.text == name and i+1 < len(body) and body[i+1].text in {'=', '+=', '-=', '++', '--'}
                         for i, t in enumerate(body))
            if binding and writes != 1:
                binding['safe'] = False
            bindings[name] = binding
        # Scope constructs whose bindings are not modeled must not borrow a
        # same-named field. This deliberately sacrifices some matches.
        for index, token in enumerate(body[:-1]):
            if token.kind == 'id' and token.text in bindings and index > 0:
                previous, following = body[index-1], body[index+1]
                binding = bindings[token.text]
                looks_declared = (previous.kind == 'id' or previous.text in {'>', ']'}) and following.text in {'=', ';', ':', ',', ')'}
                if looks_declared and previous.text not in {'return', 'throw', 'new', 'case'} and (not binding or binding['index'] != token.index):
                    bindings[token.text] = None
        skipped = set()
        for index, token in enumerate(body):
            absolute = token.index
            if token.text == '->':
                after = absolute + 1
                if self.tokens[after].text == '{':
                    stop = self.pairs[after]
                else:
                    stop = after
                    while stop < block[1] and self.tokens[stop].text not in {';', ','}:
                        if self.tokens[stop].text in {'(', '[', '{'}:
                            stop = self.pairs[stop]
                        stop += 1
                skipped.update(range(absolute, stop + 1))
            elif token.text in {'class', 'interface', 'record', 'enum'} and (index == 0 or body[index-1].text != '.'):
                opening = self.until(absolute, '{')
                if opening < block[1]:
                    skipped.update(range(absolute, self.pairs[opening] + 1))
            elif token.text == '{' and index > 0 and body[index-1].text == ')':
                opening = self.pairs[body[index-1].index]
                before = opening - 1
                while before >= block[0] and (self.tokens[before].kind == 'id' or self.tokens[before].text == '.'):
                    if self.tokens[before].text == 'new':
                        skipped.update(range(absolute, self.pairs[absolute] + 1))
                        break
                    before -= 1
        for i in range(block[0], block[1]-1):
            token = self.tokens[i]
            if i in skipped:
                continue
            if token.kind != 'id' or self.tokens[i+1].text != '(':
                continue
            end = self.pairs[i+1]
            args = split(self.tokens[i+2:end])
            if not args or i == 0 or self.tokens[i-1].text != '.':
                continue
            receiver_end = i-1
            receiver_start = receiver_end-1
            while receiver_start >= block[0] + 2 and self.tokens[receiver_start-1].text == '.' and self.tokens[receiver_start-2].kind == 'id':
                receiver_start -= 2
            receiver = spelling(self.tokens[receiver_start:receiver_end])
            key = '@field:' + receiver[5:] if receiver.startswith('this.') else receiver
            binding = bindings.get(key)
            client = binding['type'] if binding else ''
            if token.text in REST_METHODS and client == REST:
                self.outbound(token, args[0], bindings, class_name, REST + '.' + token.text)
            elif token.text == 'newBuilder' and self.qualify(receiver) == REQUEST and receiver not in bindings and len(args) == 1:
                self.outbound(token, args[0], bindings, class_name, REQUEST + '.newBuilder', declaration=True)
            elif token.text == 'uri':
                direct = client == REQUEST + '.Builder'
                if self.tokens[receiver_end-1].text == ')':
                    call_open = self.pairs[receiver_end-1]
                    if call_open >= 3 and self.tokens[call_open-1].text == 'newBuilder' and self.tokens[call_open-2].text == '.':
                        j = call_open-3
                        while j >= block[0]+2 and self.tokens[j-1].text == '.' and self.tokens[j-2].kind == 'id':
                            j -= 2
                        owner = spelling(self.tokens[j:call_open-2])
                        direct = self.qualify(owner) == REQUEST and owner not in bindings
                if direct:
                    self.outbound(token, args[0], bindings, class_name, REQUEST + '.Builder.uri', declaration=True)

    def outbound(self, token, expression, bindings, class_name, api, declaration=False):
        target, reference, evidence = self.value(expression, bindings, class_name)
        target = self.safe_target(target)
        if not target.startswith(('http://', 'https://')):
            target = '<dynamic>'
        status = 'unresolved' if target == '<dynamic>' else 'declared' if declaration else 'inferred' if evidence else 'confirmed'
        evidence = evidence + [self.proof(token.line, api)]
        self.emit(self.file, token.line, 'outbound', 'http-request' if declaration else 'http-client', target, status,
                  reference=reference or 'java:' + api, evidence=evidence)


def analyze_java(source, file, emit, safe_target):
    Java(source, file, emit, safe_target).run()
