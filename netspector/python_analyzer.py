"""Bounded lexical resolution: only unique, straight-line bindings are followed."""
import ast
from collections import Counter


class Scope:
    def __init__(self, node, parent=None):
        self.parent = parent
        self.bindings = {}
        self.counts = Counter()
        self.blocked = set()
        scope = self

        class Names(ast.NodeVisitor):
            def visit_Name(self, item):
                if isinstance(item.ctx, (ast.Store, ast.Del)):
                    scope.counts[item.id] += 1

            def visit_Import(self, item):
                for alias in item.names:
                    scope.counts[alias.asname or alias.name.split('.')[0]] += 1

            def visit_ImportFrom(self, item):
                for alias in item.names:
                    scope.counts[alias.asname or alias.name] += 1

            def visit_FunctionDef(self, item):
                scope.counts[item.name] += 1

            visit_AsyncFunctionDef = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef

            def visit_Lambda(self, item):
                pass

            def visit_Global(self, item):
                scope.blocked.update(item.names)

            visit_Nonlocal = visit_Global

            def visit_MatchAs(self, item):
                if item.name:
                    scope.counts[item.name] += 1
                self.generic_visit(item)

            visit_MatchStar = visit_MatchAs

            def visit_MatchMapping(self, item):
                if item.rest:
                    scope.counts[item.rest] += 1
                self.generic_visit(item)

            def visit_ExceptHandler(self, item):
                if item.name:
                    scope.counts[item.name] += 1
                self.generic_visit(item)

        for statement in node.body:
            Names().visit(statement)
        if hasattr(node, 'args'):
            args = node.args
            for arg in args.posonlyargs + args.args + args.kwonlyargs + ([args.vararg] if args.vararg else []) + ([args.kwarg] if args.kwarg else []):
                self.counts[arg.arg] += 1
        for statement in node.body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        self.bindings[target.id] = ('value', statement.value, statement.lineno, statement.col_offset)
            elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                self.bindings[statement.target.id] = ('value', statement.value, statement.lineno, statement.col_offset)
            elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                for alias in statement.names:
                    name = alias.asname or (alias.name.split('.')[0] if isinstance(statement, ast.Import) else alias.name)
                    full = (alias.name if alias.asname else alias.name.split('.')[0]) if isinstance(statement, ast.Import) else f'{statement.module}.{alias.name}'
                    self.bindings[name] = ('import', full, statement.lineno, statement.col_offset)

    def lookup(self, name, position):
        if name in self.blocked:
            return None
        if name in self.counts:
            binding = self.bindings.get(name)
            if self.counts[name] == 1 and binding and (binding[2], binding[3]) < position:
                return binding, self
            return None
        return self.parent.lookup(name, position) if self.parent else None


def analyze(source, file, emit, safe_target):
    tree = ast.parse(source)
    # A global/nonlocal write makes that name unsafe to propagate anywhere.
    mutated = {name for n in ast.walk(tree) if isinstance(n, (ast.Global, ast.Nonlocal)) for name in n.names}
    module = Scope(tree)
    module.blocked.update(mutated)

    def dotted(node, scope):
        if isinstance(node, ast.Name):
            found = scope.lookup(node.id, (node.lineno, node.col_offset))
            if found and found[0][0] == 'import':
                return found[0][1]
        elif isinstance(node, ast.Attribute):
            prefix = dotted(node.value, scope)
            return f'{prefix}.{node.attr}' if prefix else ''
        return ''

    def value(node, scope, seen=()):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value, None, []
        if isinstance(node, ast.Name) and node.id not in seen:
            found = scope.lookup(node.id, (node.lineno, node.col_offset))
            if found and found[0][0] == 'value':
                binding, owner = found
                target, ref, evidence = value(binding[1], owner, seen + (node.id,))
                return target, ref or f'constant:{node.id}', evidence + [dict(file=file, line=binding[2], reference=node.id)]
        if isinstance(node, ast.Call) and dotted(node.func, scope) in {'os.getenv', 'os.environ.get'}:
            key = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == 'key'), None)
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return '<dynamic>', f'env:{key.value}', []
        if isinstance(node, ast.Subscript) and dotted(node.value, scope) == 'os.environ':
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                return '<dynamic>', f'env:{node.slice.value}', []
        return '<dynamic>', None, []

    class Visitor(ast.NodeVisitor):
        def __init__(self, scope):
            self.scope = scope

        def visit_FunctionDef(self, node):
            for decorator in node.decorator_list:
                self.visit(decorator)
            child = Scope(node, self.scope)
            child.blocked.update(mutated)
            visitor = Visitor(child)
            for statement in node.body:
                visitor.visit(statement)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node):
            # Class/method attribute resolution is intentionally unsupported.
            pass

        def visit_Lambda(self, node):
            pass

        def visit_ListComp(self, node):
            pass

        visit_SetComp = visit_ListComp
        visit_DictComp = visit_ListComp
        visit_GeneratorExp = visit_ListComp

        def visit_Call(self, node):
            owner = ''
            method = node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if isinstance(node.func, ast.Attribute):
                owner = dotted(node.func.value, self.scope)
                if not owner and isinstance(node.func.value, ast.Name):
                    found = self.scope.lookup(node.func.value.id, (node.lineno, node.col_offset))
                    if found and found[0][0] == 'value' and isinstance(found[0][1], ast.Call):
                        owner = dotted(found[0][1].func, found[1])
            methods = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}
            outbound = method in methods and owner in {'requests', 'httpx', 'requests.Session', 'httpx.Client', 'httpx.AsyncClient'}
            inbound = method in methods | {'websocket', 'api_route'} and owner in {'fastapi.FastAPI', 'fastapi.APIRouter'}
            if outbound or inbound:
                arg = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg in {'url', 'path'}), None)
                target, ref, evidence = value(arg, self.scope)
                if outbound:
                    target = safe_target(target)
                status = 'unresolved' if target == '<dynamic>' else ('inferred' if evidence else ('confirmed' if outbound else 'declared'))
                emit(file, node.lineno, 'outbound' if outbound else 'inbound', 'http-client' if outbound else 'route', target, status,
                     protocol=None if outbound else ('websocket' if method == 'websocket' else 'http'), reference=ref, evidence=evidence)
            self.generic_visit(node)

    Visitor(module).visit(tree)
