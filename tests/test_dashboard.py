from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_dashboard_compose_is_lan_bound_and_read_only():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"192.168.68.105:8080:8080"' in compose
    assert '"./project/exports:/exports:ro"' in compose
    assert '"/volume1:/volume1:ro"' in compose
    assert "read_only: true" in compose
    assert "/var/run/docker.sock" not in compose


def test_dashboard_has_stable_routes_and_only_review_mutations():
    source = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/coredashboard")' in source
    assert '@app.get("/api/v1/overview")' in source
    assert '@app.get("/coreworkset")' in source
    assert '@app.get("/api/v1/workset")' in source
    assert source.count("@app.post") == 3
    assert "INSERT INTO public.document_review_events" in source
    assert "INSERT INTO public.document_review_batches" in source
    assert "UPDATE public." not in source
    assert "DELETE FROM" not in source


def test_dashboard_frontend_uses_relative_api_and_refreshes():
    source = (ROOT / "dashboard" / "static" / "app.js").read_text(encoding="utf-8")
    assert "fetch('/api/v1/overview'" in source
    assert "setInterval(refresh,10000)" in source


def test_core_cli_exposes_dashboard_lifecycle():
    source = (ROOT / "tools" / "runtime" / "core").read_text(encoding="utf-8")
    assert 'core dashboard deploy' in source
    assert 'compose build dashboard' in source
    assert 'compose ps dashboard' in source


def test_workset_portal_is_parameterized_review_only_and_mobile():
    backend = (ROOT / "dashboard" / "app.py").read_text(encoding="utf-8")
    frontend = (ROOT / "dashboard" / "static" / "workset.js").read_text(encoding="utf-8")
    page = (ROOT / "dashboard" / "static" / "workset.html").read_text(encoding="utf-8")
    css = (ROOT / "dashboard" / "static" / "workset.css").read_text(encoding="utf-8")
    assert "v_active_document_workset" in backend
    assert "v_current_file_classification" in backend
    assert "ILIKE %s" in backend
    assert '"database_writes": False' in backend
    assert '"file_mutations": False' in backend
    assert "INSERT INTO public.document_review_events" in backend
    assert "UPDATE public." not in backend
    assert "DELETE FROM" not in backend
    assert "fetch(`/api/v1/workset?" in frontend
    assert 'id="worksetFamily"' in page
    assert 'id="worksetReview"' in page
    assert 'id="worksetDecision"' in page
    assert 'value="pending"' in page
    assert "data-decision=\"accepted\"" in frontend
    assert "corrected_document_family_code" in frontend
    assert "review-complete" in frontend
    assert "Alles in deze selectie is beoordeeld" in frontend
    assert "toggleHistory" in frontend
    assert "Menselijk oordeel" in frontend
    assert "Nieuwe categorie, familie of doelpad voorstellen" in frontend
    assert "proposed_category_label" in frontend
    assert "corrected_category_code" in frontend
    assert "Meer…" in frontend
    assert "family-search" in frontend
    assert "CORE-voorstel" in frontend
    assert "/reviews/export?format=csv" in page
    assert "/reviews/export?format=json" in page
    assert 'id="bulkSelectAll"' in page
    assert 'id="bulkReviewDialog"' in page
    assert "privacy_confirmation_included" in backend
    assert "/reviews/bulk/preview" in frontend
    assert "Geselecteerde voorstellen akkoord" in page
    assert "wsEsc" in frontend
    assert "Kopieer SMB-pad" in frontend
    assert 'name="viewport"' in page
    assert "@media(max-width:760px)" in css
