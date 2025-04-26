# tests/test_cli.py
import os
import pytest
from click.testing import CliRunner

# import your CLI entry point
from doccli.main import cli

@pytest.fixture(autouse=True)
def clear_session(tmp_path, monkeypatch):
    # point session file into a temp dir so real ~/.doccli_session isn’t touched
    session_file = tmp_path / ".doccli_session"
    monkeypatch.setenv("HOME", str(tmp_path))
    yield
    # cleanup if needed

def test_help_shows_login_when_logged_out():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    # login & register should appear
    assert "login" in result.output
    assert "register" in result.output

def test_register_student_creates_user(tmp_path, monkeypatch):
    runner = CliRunner()
    # use a temporary DB
    db = tmp_path / "metadata.db"
    monkeypatch.setenv("DB_PATH", str(db))
    # simulate user input: password & confirm
    result = runner.invoke(cli, ["register", "Alice", "alice@example.com", "student"],
                           input="pass123\npass123\n")
    assert result.exit_code == 0
    assert "registered" in result.output.lower()
    # confirm the user is in the DB
    import sqlite3
    conn = sqlite3.connect(str(db))
    cur = conn.execute("SELECT name, email, role FROM users")
    row = cur.fetchone()
    conn.close()
    assert row == ("Alice", "alice@example.com", "student")
