from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_renders_initial_workspace_without_api_calls():
    dashboard = Path(__file__).resolve().parents[1] / "dashboard" / "app.py"

    app = AppTest.from_file(str(dashboard)).run(timeout=20)

    assert not app.exception
    assert app.title[0].value == "AlphaTest Strategy Backtester"
    assert "Manage saved configurations" in [checkbox.label for checkbox in app.checkbox]
