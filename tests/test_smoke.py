# tests/test_smoke.py
import os
import json
import sqlite3
import pytest
from click.testing import CliRunner

import doccli.main as main

@pytest.fixture(autouse=True)
def isolate_fs(tmp_path, monkeypatch):
    """
    Redirect all file-based paths (DB, session, dirs) into a fresh temp directory.
    """
    # point HOME → tmp for session file
    monkeypatch.setenv("HOME", str(tmp_path))
    # override all module constants
    main.DB_PATH            = str(tmp_path / "metadata.db")
    main.DOCS_DIR           = str(tmp_path / "docs")
    main.QUIZ_DIR           = str(tmp_path / "quizzes")
    main.ANS_KEY_DIR        = str(tmp_path / "answer_keys")
    main.STUDENT_RESP_DIR   = str(tmp_path / "student_responses")
    main.SESSION_FILE       = str(tmp_path / ".doccli_session")

    # ensure dirs exist for commands
    for d in (main.DOCS_DIR, main.QUIZ_DIR, main.ANS_KEY_DIR, main.STUDENT_RESP_DIR):
        os.makedirs(d, exist_ok=True)

    # Initialize the empty database
    main.init_db()

    yield  # tests run below

@pytest.fixture
def runner():
    return CliRunner()

def test_help_loads(runner):
    """Smoke: --help should exit zero and list top-level commands."""
    result = runner.invoke(main.cli, ["--help"])
    assert result.exit_code == 0
    # you expect login/register when logged out
    assert "login" in result.output
    assert "register" in result.output
    assert "upload" in result.output  # even if hidden later, show in help when logged out

def test_list_docs_requires_login(runner):
    """Smoke: list-docs without login should abort."""
    result = runner.invoke(main.cli, ["list-docs"])
    assert result.exit_code != 0
    assert "Not logged in" in result.output

def test_student_register_and_login(runner, monkeypatch):
    """Smoke: student self-register then login produces session file."""
    # stub getpass to supply a password twice for register
    pw_iter = iter(["secretpwd", "secretpwd"])
    monkeypatch.setattr(main.getpass, "getpass", lambda prompt="": next(pw_iter))

    # register
    reg = runner.invoke(main.cli, ["register", "Test Student", "stud@example.com", "student"])
    assert reg.exit_code == 0
    assert "registered" in reg.output.lower()

    # DB should contain the user
    conn = sqlite3.connect(main.DB_PATH)
    cur = conn.execute("SELECT name,email,role FROM users")
    user = cur.fetchone()
    conn.close()
    assert user == ("Test Student", "stud@example.com", "student")

    # stub getpass for login
    monkeypatch.setattr(main.getpass, "getpass", lambda prompt="": "secretpwd")
    # login
    log = runner.invoke(main.cli, ["login", "stud@example.com"])
    assert log.exit_code == 0
    assert "logged in as test student" in log.output.lower()

    # session file exists and contains correct fields
    sess = json.loads(open(main.SESSION_FILE).read())
    assert sess["email"] == "stud@example.com"
    assert sess["role"] == "student"

def test_list_docs_after_login(runner, monkeypatch):
    """Smoke: after login, list-docs runs (no docs yet) with exit code 0."""
    # prepare a user & session
    monkeypatch.setenv("HOME", str(runner.isolated_filesystem().tmp_path))
    # register & login
    pw_iter = iter(["pw","pw"])
    monkeypatch.setattr(main.getpass, "getpass", lambda prompt="": next(pw_iter))
    runner.invoke(main.cli, ["register", "Stu", "a@b.com", "student"])
    monkeypatch.setattr(main.getpass, "getpass", lambda prompt="": "pw")
    runner.invoke(main.cli, ["login", "a@b.com"])

    # now list-docs
    result = runner.invoke(main.cli, ["list-docs"])
    assert result.exit_code == 0
    # no docs => no output, but clean exit
    assert result.output.strip() == ""

def test_logout_clears_session(runner, monkeypatch):
    """Smoke: logout removes session file and subsequent commands require login."""
    # stub session file into place
    session = {"user_id":1, "name":"X","email":"x@x","role":"student"}
    open(main.SESSION_FILE,"w").write(json.dumps(session))

    # logout
    result = runner.invoke(main.cli, ["logout"])
    assert result.exit_code == 0
    assert "logged out" in result.output.lower()
    assert not os.path.exists(main.SESSION_FILE)

    # now list-docs should require login again
    again = runner.invoke(main.cli, ["list-docs"])
    assert again.exit_code != 0
    assert "not logged in" in again.output.lower()
