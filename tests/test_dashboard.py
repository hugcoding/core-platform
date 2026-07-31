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
    assert "@app.post" not in source


def test_dashboard_frontend_uses_relative_api_and_refreshes():
    source = (ROOT / "dashboard" / "static" / "app.js").read_text()
    assert "fetch('/api/v1/overview'" in source
    assert "setInterval(refresh,10000)" in source
    assert "addEventListener('click',refresh)" in source
    assert "classList.add('loading')" in source


def test_core_cli_exposes_dashboard_lifecycle():
    source = (ROOT / "tools" / "runtime" / "core").read_text()
    assert 'core dashboard deploy' in source
    assert 'compose build dashboard' in source
    assert 'compose ps dashboard' in source


def test_dashboard_has_a_visible_mkdocs_page():
    navigation = (ROOT / "mkdocs.yml").read_text()
    page = (ROOT / "docs" / "wiki" / "core-pulse.md").read_text()
    assert "CORE Pulse: wiki/core-pulse.md" in navigation
    assert "core dashboard deploy" in page
    assert "core docs deploy" in page
