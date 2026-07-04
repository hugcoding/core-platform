import ast
import json


def read_text(path):
    if not path.exists():
        return ""
    return path.read_text(errors="replace")


def analyse_python_file(root, relative_path):
    path = root / relative_path
    result = {
        "file": relative_path,
        "exists": path.exists(),
        "imports": [],
        "constants": [],
        "functions": [],
        "classes": [],
        "syntax_error": None,
    }

    if not path.exists():
        return result

    text = read_text(path)

    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        result["syntax_error"] = str(e)
        return result

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                result["imports"].append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                result["imports"].append((module + "." + alias.name).strip("."))

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result["constants"].append(target.id)

        elif isinstance(node, ast.FunctionDef):
            result["functions"].append({
                "name": node.name,
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "docstring": ast.get_docstring(node) or "",
            })

        elif isinstance(node, ast.ClassDef):
            result["classes"].append({
                "name": node.name,
                "line": node.lineno,
                "docstring": ast.get_docstring(node) or "",
            })

    result["imports"] = sorted(set(result["imports"]))
    result["constants"] = sorted(set(result["constants"]))
    return result


def analyse_python_sources(root, sources):
    return {src: analyse_python_file(root, src) for src in sources}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
