#!/usr/bin/env python3
import os
import sqlite3
import datetime
import click
from openai import OpenAI
import json
import getpass
import hashlib
import functools
import shutil

# PDF text extraction
from pdfminer.high_level import extract_text

# ——— Configuration ———
DB_PATH = "metadata.db"
DOCS_DIR = "docs/"
QUIZ_DIR = "quizzes/"
ANS_KEY_DIR = "answer_keys/"
STUDENT_RESP_DIR = "student_responses/"
SESSION_FILE = os.path.expanduser("~/.doccli_session")      # Where to persist current session. Store { user_id, name, role } here.

HELP_TEXT_WIDTH = 150
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'], max_content_width=HELP_TEXT_WIDTH)

# ——— Helpers ———
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS documents (
      id INTEGER PRIMARY KEY,
      name TEXT,
      owner TEXT,
      timestamp TEXT,
      type TEXT,
      summary TEXT
    )""")
    # Users table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY,
      name TEXT,
      email TEXT UNIQUE,
      role TEXT,
      password_hash TEXT
    )""")
    conn.commit()
    conn.close()


def get_db_connection():
    return sqlite3.connect(DB_PATH)

def save_metadata(name, owner, doc_type):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(
      "INSERT INTO documents (name, owner, timestamp, type) VALUES (?, ?, ?, ?)",
      (name, owner, datetime.datetime.utcnow().isoformat(), doc_type)
    )
    conn.commit()
    conn.close()


def get_text(path):
    """Extract plain text from documents (supports .txt and .pdf)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_text(path)
    else:
        with open(path, encoding='utf-8', errors='ignore') as f:
            return f.read()


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


# Check if session file exists and load it
def load_session():
    if not os.path.exists(SESSION_FILE):
        click.echo("Not logged in. Please `login` first.")
        raise click.Abort()
    with open(SESSION_FILE, 'r') as f:
        return json.load(f)


# Decorator: Wrap CLI commands to require login (no extra args)
def require_login(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # abort if not logged in
        load_session()
        return func(*args, **kwargs)
    wrapper.requires_login = True
    return wrapper


def is_logged_in():
    return os.path.exists(SESSION_FILE)


# Decorator factory: Check if user's role is in the allow list (no extra args)
def require_role(roles):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            session = load_session()
            if session.get('role') not in roles:
                click.echo(f"Permission denied: requires one of {roles}.")
                raise click.Abort()
            return func(*args, **kwargs)
        wrapper.requires_login = True
        wrapper.roles          = set(roles)
        return wrapper
    return decorator


# ——— Custom Group to Filter Commands ———
class DocCLI(click.Group):
    def list_commands(self, ctx):
        all_cmds = super().list_commands(ctx)
        filtered = []
        logged_in = is_logged_in()
        role = None
        if logged_in:
            role = load_session().get('role')

        for name in all_cmds:
            cmd = self.commands[name]
            cb  = cmd.callback

            # -- once logged in, hide login for everyone
            if logged_in and name == "login":
                continue
            # -- once logged in, hide register for non-admins, but allow admins
            if logged_in and name == "register" and role != "admin":
                continue
            # -- always hide logout when logged out
            if not logged_in and name == "logout":
                continue

            # -- hide any command requiring login if not logged in
            if not logged_in and getattr(cb, 'requires_login', False):
                continue

            # -- hide any command requiring a role the user doesn't have
            roles_required = getattr(cb, 'roles', None)
            if roles_required and role not in roles_required:
                continue

            filtered.append(name)
        return filtered
        
    
    def get_command(self, ctx, name):
        cmd = super().get_command(ctx, name)
        if not cmd:
            return None

        cb = cmd.callback
        logged_in = is_logged_in()
        role = load_session().get('role') if logged_in else None

        # same filters as list_commands:
        # once logged in, disallow login
        if logged_in and name == "login":
            return None
        # once logged in, disallow register for non-admins
        if logged_in and name == "register" and role != "admin":
            return None
        if not logged_in and name == "logout":
            return None

        if not logged_in and getattr(cb, 'requires_login', False):
            return None

        roles_required = getattr(cb, 'roles', None)
        if roles_required and role not in roles_required:
            return None

        return cmd
    

# ——— CLI Commands ———

# Click should use filtered command list
@click.group(cls=DocCLI, context_settings = CONTEXT_SETTINGS)
def cli():
    """Document Analyzer CLI"""
    os.makedirs(DOCS_DIR,         exist_ok=True)
    os.makedirs(QUIZ_DIR,         exist_ok=True)
    os.makedirs(ANS_KEY_DIR,      exist_ok=True)
    os.makedirs(STUDENT_RESP_DIR, exist_ok=True)
    init_db()


# Register: Prompt and check password. Hash and store user info with unique email.
@cli.command()
@click.argument('name')
@click.argument('email')
@click.argument('role', type=click.Choice(['teacher','student','admin']))
def register(name, email, role):
    """Register a new user: <name> <email> <role>"""

    # if you’re not logged in yet, you can only self-register as a student
    if not is_logged_in() and role != 'student':
        click.echo("Self-registration is open only for students. Ask an admin to create teacher accounts.")
        return
    
    conn = get_db_connection()
    c = conn.cursor()

    if role == 'admin':
        c.execute("SELECT COUNT(*) FROM users WHERE role='admin'")
        if c.fetchone()[0] > 0:
            click.echo('An admin already exists. Cannot register another admin.')
            conn.close()
            return

    password = getpass.getpass('Password: ')
    confirm = getpass.getpass('Confirm Password: ')
    if password != confirm:
        click.echo('Passwords do not match.')
        return
    pwd_hash = hash_password(password)
    try:
        c.execute(
            "INSERT INTO users (name,email,role,password_hash) VALUES (?,?,?,?)",
            (name,email,role,pwd_hash)
        )
        conn.commit()
        click.echo(f"User {name} ({role}) registered.")
    except sqlite3.IntegrityError:
        click.echo('Error: email already registered.')
    finally:
        conn.close()


# Login: Look up user by email, check password, and store session info.
@cli.command()
@click.argument('email')
def login(email):
    """Log in as existing user"""
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id,name,role,password_hash FROM users WHERE email=?", (email,))
    row = c.fetchone()
    conn.close()
    if not row:
        click.echo('User not found.')
        return
    user_id,name,role,pwd_hash = row
    password = getpass.getpass('Password: ')
    if hash_password(password) != pwd_hash:
        click.echo('Invalid password.')
        return
    session = {
    'user_id': user_id,
    'name':    name,
    'email':   email,   
    'role':    role
    }
    with open(SESSION_FILE,'w') as f:
        json.dump(session, f)
    click.echo(f"Logged in as {name} ({role}).")


# Logout: Remove session file.
@cli.command()
def logout():
    """Log out current user"""
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)
        click.echo('Logged out.')
    else:
        click.echo('Not logged in.')



@cli.command()
@require_login
@require_role(['teacher','admin'])
@click.argument("file", type=click.Path(exists=True))
def upload(file):
    """Upload a document (PDF or txt).  Owner is set to the current user."""
    # load the session now that we're inside the command
    session = load_session()
    owner   = session['email']

    ext = os.path.splitext(file)[1].lower()
    if ext not in ['.pdf', '.txt']:
        click.echo("Unsupported file type. Only .pdf and .txt are allowed.")
        return

    dest = os.path.join(DOCS_DIR, os.path.basename(file))
    # copy original into docs/ (doesn’t delete the source)
    shutil.copy2(file, dest)

    # now record with the real owner
    save_metadata(os.path.basename(file), owner, ext)
    click.echo(f"Uploaded {dest} (owner: {owner}).")


@cli.command()
@require_login
@click.argument("docname")
def summarize(docname):
    """Generate a summary via OpenAI"""
    click.echo("Generating summary...")
    client = OpenAI(
			# This is the default and can be omitted
			api_key=os.environ.get("OPENAI_API_KEY"),
		)
    
    path = os.path.join(DOCS_DIR, docname)
    if not os.path.exists(path):
        click.echo("Document not found. Are you missing .pdf or .txt?")
        return
    text = get_text(path)
    prompt = f"Summarize this:\n\n{text}"
    response = client.responses.create(
			model="gpt-4o-mini",
			input=prompt,
			#temperature=0.6,
			#max_tokens=1500
		)
    response_text = response.output_text
    click.echo(response_text)


@cli.command()
@require_login
@require_role(['teacher','admin'])
@click.argument("docname")
@click.option("--n", default=5, help="Number of quiz questions")
def quiz(docname, n):
    """<docname> <num questions> Auto‑generate a quiz"""
    click.echo(f"Generating {n} quiz questions for {docname}...")
    client = OpenAI(
			# This is the default and can be omitted
			api_key=os.environ.get("OPENAI_API_KEY"),
		)
    
    path = os.path.join(DOCS_DIR, docname)
    if not os.path.exists(path):
        click.echo("Document not found.")
        return
    text = get_text(path)
    prompt = (
      f"Create {n} quiz questions (with multiple‑choice options) "
      f"based on the following content, along with an easily formatted answer key:\n\n{text}"
      f"\n\nAnswer key format should be:\n"
      f"1. B) Answer\n"
    )
    response = client.responses.create(
			model="gpt-4o-mini",
			input=prompt,
			#temperature=0.6,
			#max_tokens=1500
		)
    response_text = response.output_text
    # Split out questions vs answer key
    if "Answer Key" in response_text:
        questions_part, answer_key_part = response_text.split("Answer Key", 1)
        answer_key_part = "Answer Key" + answer_key_part
    else:
        questions_part = response_text
        answer_key_part = ""

    # Write the quiz questions
    quiz_file = os.path.join(QUIZ_DIR, f"{docname}_quiz.txt")
    with open(quiz_file, "w", encoding="utf-8") as f:
        f.write(questions_part.strip())
        f.write("\n\nAnswer files should be in the format:\nFirst Last, A, B, C, D")
    click.echo(f"Quiz saved to {quiz_file}")

    # Write the answer key (if present)
    if answer_key_part:
        ans_file = os.path.join(ANS_KEY_DIR, f"{docname}_answer_key.txt")
        with open(ans_file, "w", encoding="utf-8") as f:
            f.write(answer_key_part.strip())
        click.echo(f"Answer key saved to {ans_file}")
    


@cli.command()
@require_login
@require_role(['teacher','admin'])
@click.argument("response_file", type=click.STRING)
@click.argument("answer_key_file", type=click.STRING)
def grade(response_file, answer_key_file):
    """<response_file> <answer_key_file> Grade quiz responses against the answer key"""
    click.echo("Grading quiz responses...")
    # Parse answer key
    answer_key_file = os.path.join(ANS_KEY_DIR, answer_key_file)
    with open(answer_key_file, encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    #click.echo(f"lines: {lines}")
    # Locate 'Answer Key' section
    if 'Answer Key' in lines:
        start = lines.index('Answer Key') + 1
    else:
        start = 0
    key_lines = lines[start:]
    #click.echo(f"key_lines: {key_lines}")
    correct = []
    for line in key_lines:
        if ')' in line:
            letter = line.split(')')[0].strip()
            correct.append(letter.upper())
    # Parse student responses (supports multiple lines)
    response_file = os.path.join(STUDENT_RESP_DIR, response_file)
    with open(response_file, encoding='utf-8') as f:
        resp_lines = [line.strip() for line in f if line.strip()]
    #click.echo(f"resp_lines: {resp_lines}")
    for resp in resp_lines:
        parts = [p.strip() for p in resp.split(',')]
        student = parts[0]
        answers = [a.upper() for a in parts[1:]]
        #click.echo(f"answers: {answers}")
        total = len(correct)
        scored = sum(1 for a, k in zip(answers, correct) if a == k[-1])
        click.echo(f"Student: {student}")
        click.echo(f"Score: {scored}/{total}")
        click.echo("Question breakdown:")
        for idx, (a, k) in enumerate(zip(answers, correct), start=1):
            if a == k[-1]:
                status = "Correct"
            else:
                status = f"Incorrect (Correct: {k[-1]})"
            click.echo(f" {idx}. Your: {a} | {status}")
        click.echo("-" * 40)


@cli.command()
@require_login
def list_docs():
    """List uploaded documents"""
    conn = sqlite3.connect(DB_PATH)
    for row in conn.execute("SELECT id, name, owner, timestamp, type FROM documents"):
        click.echo(f"{row[0]} | {row[1]} | {row[2]} | {row[4]} @ {row[3]}")
    conn.close()


@cli.command('list-quizzes')
@require_login
def list_quizzes():
    """List all generated quiz files."""
    # assumes quizzes are saved as <docname>_quiz.txt under DOCS_DIR
    quizzes = [f for f in os.listdir(QUIZ_DIR) if f.endswith('_quiz.txt')]
    if not quizzes:
        click.echo("No quizzes found.")
        return
    click.echo("Available quizzes:")
    for q in quizzes:
        click.echo(f"  • {q}")


@cli.command('read-quiz')
@require_login
@click.argument('quiz_filename', type=click.STRING)
def read_quiz(quiz_filename):
    """
    Display the contents of a quiz file.
    Pass in the exact filename as listed by `list-quizzes`.
    """
    path = os.path.join(QUIZ_DIR, quiz_filename)
    if not os.path.exists(path):
        click.echo(f"Quiz file not found: {quiz_filename}")
        return
    click.echo(f"--- {quiz_filename} ---\n")
    with open(path, 'r', encoding='utf-8') as f:
        click.echo(f.read())


@cli.command('delete-doc')
@require_login
@require_role(['teacher','admin'])
@click.argument('name', type=click.STRING)
def delete_doc(name):
    """
    Teachers can delete a document by its name, if they are the owner.
    """
    # load session to check ownership
    session = load_session()

    conn = get_db_connection()
    c = conn.cursor()

    # look up the doc
    c.execute("SELECT name, owner FROM documents WHERE name = ?", (name,))
    row = c.fetchone()
    if not row:
        click.echo(f"No document found with name {name}.")
        conn.close()
        return

    name, owner = row

    # teachers may only delete their own
    if session['role'] == 'teacher' and owner != session['email']:
        click.echo("Permission denied: you can only delete documents you own.")
        conn.close()
        return

    # remove the file if it exists
    path = os.path.join(DOCS_DIR, name)
    if os.path.exists(path):
        os.remove(path)

    # remove the metadata row
    c.execute("DELETE FROM documents WHERE name = ?", (name,))
    conn.commit()
    conn.close()

    click.echo(f"Deleted document ({name}).")






if __name__ == "__main__":
    cli()
