from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_dashboard_compose_is_lan_bound_and_read_only():
    compose = (ROOT / "docker-compose.yml").read_text()
    assert '"192.168.68.105:8080:8080"' in compose
    assert '"./project/exports:/exports:ro"' in compose
    assert '"/volume1:/volume1:ro"' in compose
    assert "read_only: true" in compose
    assert "/var/run/docker.sock" not in compose


def test_dashboard_has_stable_routes_and_no_command_endpoint():
    source = (ROOT / "dashboard" / "app.py").read_text()
    assert '@app.get("/coredashboard")' in source
    assert '@app.get("/api/v1/overview")' in source
    assert '@app.get("/coreworkset")' in source
    assert '@app.get("/api/v1/workset")' in source
    assert "@app.post" not in source


def test_dashboard_frontend_uses_relative_api_and_refreshes():
    source = (ROOT / "dashboard" / "static" / "app.js").read_text()
    assert "fetch('/api/v1/overview'" in source
    assert "setInterval(refresh,10000)" in source


def test_core_cli_exposes_dashboard_lifecycle():
    source = (ROOT / "tools" / "runtime" / "core").read_text()
    assert 'core dashboard deploy' in source
    assert 'compose build dashboard' in source
    assert 'compose ps dashboard' in source


def test_workset_portal_is_parameterized_read_only_and_mobile():
    backend = (ROOT / "dashboard" / "app.py").read_text()
    frontend = (ROOT / "dashboard" / "static" / "workset.js").read_text()
    page = (ROOT / "dashboard" / "static" / "workset.html").read_text()
    css = (ROOT / "dashboard" / "static" / "workset.css").read_text()
    assert "v_active_document_workset" in backend
    assert "v_current_file_classification" in backend
    assert "ILIKE %s" in backend
    assert "LIMIT %s OFFSET %s" in backend
    assert '"database_writes": False' in backend
    assert '"file_mutations": False' in backend
    assert "INSERT INTO" not in backend
    assert "UPDATE public." not in backend
    assert "DELETE FROM" not in backend
    assert "fetch(`/api/v1/workset?" in frontend
    assert "wsEsc" in frontend
    assert "Kopieer SMB-pad" in frontend
    assert 'name="viewport"' in page
    assert "@media(max-width:760px)" in css
