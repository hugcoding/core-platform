import ast
from pathlib import Path
from tools.docs.io_utils import read_text


def _import_name(node):
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return [(module + "." + alias.name).strip(".") for alias in node.names]
    return []


def analyze_python_file(root, relative_path):
    path = Path(root) / relative_path
    result = {
        "file": relative_path,
        "exists": path.exists(),
        "line_count": 0,
        "imports": [],
        "constants": [],
        "functions": [],
        "classes": [],
        "redis_keys": [],
        "sql_statements": [],
        "syntax_error": None,
    }

    if not path.exists():
        return result

    text = read_text(path)
    result["line_count"] = len(text.splitlines())

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        result["syntax_error"] = str(exc)
        return result

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            result["imports"].extend(_import_name(node))

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    result["constants"].append({
                        "name": target.id,
                        "line": node.lineno,
                    })

                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        value = node.value.value
                        if "lock" in value.lower() or "stream" in value.lower() or "heartbeat" in value.lower():
                            result["redis_keys"].append(value)

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

        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value.strip()
            upper = value.upper()
            if any(word in upper for word in ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "ON CONFLICT", "CREATE TABLE"]):
                result["sql_statements"].append({
                    "line": getattr(node, "lineno", None),
                    "snippet": value[:500],
                })

    result["imports"] = sorted(set(result["imports"]))
    result["redis_keys"] = sorted(set(result["redis_keys"]))
    result["constants"] = sorted(result["constants"], key=lambda x: x["name"])
    result["functions"] = sorted(result["functions"], key=lambda x: x["line"])
    result["classes"] = sorted(result["classes"], key=lambda x: x["line"])

    return result


def analyze_python_files(root, files):
    return {filename: analyze_python_file(root, filename) for filename in files}
