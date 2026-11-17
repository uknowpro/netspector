"""Read UTF-8 Java .properties files, including continuations and escapes."""
import re


def unescape(value):
    def replace(match):
        escaped = match.group()[1:]
        if escaped.startswith('u'):
            if len(escaped) != 5:
                raise ValueError('Invalid properties Unicode escape')
            return chr(int(escaped[1:], 16))
        return {'t': '\t', 'n': '\n', 'r': '\r', 'f': '\f'}.get(escaped, escaped)
    decoded = re.sub(r'\\(?:u.{0,4}|.)', replace, value)
    return decoded.encode('utf-16', 'surrogatepass').decode('utf-16')


def properties(source):
    pending, first_line = '', None
    for number, raw in enumerate(source.splitlines(), 1):
        if first_line is None:
            if not raw.lstrip() or raw.lstrip().startswith(('#', '!')):
                continue
            first_line = number
            pending = raw.lstrip()
        else:
            pending += raw.lstrip()
        slashes = len(pending) - len(pending.rstrip('\\'))
        if slashes % 2:
            pending = pending[:-1]
            continue
        yield parse(pending, first_line)
        first_line, pending = None, ''
    if first_line is not None:
        yield parse(pending, first_line)


def parse(line, number):
    end, escaped = 0, False
    while end < len(line):
        if not escaped and (line[end] in '=:' or line[end].isspace()):
            break
        if line[end] == '\\' and not escaped:
            escaped = True
        else:
            escaped = False
        end += 1
    start = end
    while start < len(line) and line[start].isspace():
        start += 1
    if start < len(line) and line[start] in '=:':
        start += 1
    while start < len(line) and line[start].isspace():
        start += 1
    return unescape(line[:end]), unescape(line[start:]), number
