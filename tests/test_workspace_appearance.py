"""Regression checks for moving the same workspace between presentations."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

SCRIPT = '''
from pathlib import Path
import streamlit as st
from app.ui.appearance import appearance_controls, render_navigation
from app.ui.workspace import home
st.set_page_config(layout="wide")
app_layout = appearance_controls()
menu = render_navigation(app_layout)
if menu == "Home":
    home({"projects_path": Path(st.session_state["test_root"]) / "projects.json",
          "workspace_settings_path": Path(st.session_state["test_root"]) / "settings.json",
          "business_type": "카페"})
else:
    st.header(menu)
'''


def workspace(tmp_path):
    app = AppTest.from_string(SCRIPT, default_timeout=15)
    app.session_state["test_root"] = str(tmp_path)
    return app


def test_navigation_survives_layout_theme_and_settings(tmp_path):
    app = workspace(tmp_path).run()
    app.radio(key="workspace_nav").set_value("Studio").run()
    for key in ["layout_app", "theme_switch", "layout_web"]:
        app.button(key=key).click().run()
        assert not app.exception
        assert app.session_state["active_menu"] == "Studio"
    app.button(key="open_settings").click().run()
    assert app.session_state["active_menu"] == "Settings"
    assert app.radio(key="workspace_nav").value is None
    app.radio(key="workspace_nav").set_value("Home").run()
    assert app.session_state["theme"] == "dark"
    assert not app.exception


def test_new_project_keeps_draft_across_theme_change(tmp_path):
    app = workspace(tmp_path).run()
    app.button(key="start_project").click().run()
    app.text_input[0].set_value("비 오는 날의 라떼").run()
    app.button(key="theme_switch").click().run()
    assert app.text_input[0].value == "비 오는 날의 라떼"
    next(button for button in app.button if button.label == "프로젝트 만들기").click().run()
    assert not app.exception
    assert app.session_state["active_menu"] == "Studio"
    assert app.session_state["active_project_id"]
    assert "비 오는 날의 라떼" in (tmp_path / "projects.json").read_text()


def test_url_preferences_and_empty_project_validation(tmp_path):
    app = workspace(tmp_path)
    app.query_params.update({"layout": "app", "theme": "dark", "code": "keep-callback"})
    app.run()
    assert app.session_state["layout"] == "app"
    assert app.session_state["theme"] == "dark"
    app.button(key="start_project").click().run()
    next(button for button in app.button if button.label == "프로젝트 만들기").click().run()
    assert app.warning
    assert not (tmp_path / "projects.json").exists()
    app.button(key="layout_web").click().run()
    assert app.query_params["code"] == ["keep-callback"]
    assert not app.exception
