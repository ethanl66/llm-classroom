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

# PDF text extraction
from pdfminer.high_level import extract_text

# ——— Configuration ———
DB_PATH = "metadata.db"
DOCS_DIR = "docs/"
SESSION_FILE = os.path.expanduser("~/.doccli_session")      # Where to persist current session. Store { user_id, name, role } here.

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


# Decorator: Wrap CLI commands to require login. Pass session as first argument.
def require_login(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # abort if not logged in
        session = load_session()
        return func(session, *args, **kwargs)
    return wrapper


def is_logged_in():
    return os.path.exists(SESSION_FILE)


# Decorator factory: Check if user's role is in the allow list.
def require_role(roles):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(session, *args, **kwargs):
            if session.get('role') not in roles:
                click.echo(f"Permission denied: requires one of {roles}.")
                raise click.Abort()
            return func(session, *args, **kwargs)
        return wrapper
    return decorator


# ——— Custom Group to Filter Commands ———
class DocCLI(click.Group):
    def list_commands(self, ctx):
        cmds = super().list_commands(ctx)
        if is_logged_in():
            # once logged in, hide login & register
            return [c for c in cmds if c not in ("login", "register")]
        else:
            # when logged out, hide logout
            return [c for c in cmds if c != "logout"]
    
    def get_command(self, ctx, name):
        # enforce the same filter on direct invocation
        if is_logged_in() and name in ("login", "register"):
            return None
        if not is_logged_in() and name == "logout":
            return None
        return super().get_command(ctx, name)
    

# ——— CLI Commands ———

@click.group(cls=DocCLI)
def cli():
    """Document Analyzer CLI"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    init_db()


# Register: Prompt and check password. Hash and store user info with unique email.
@cli.command()
@click.argument('name')
@click.argument('email')
@click.argument('role', type=click.Choice(['teacher','student','admin']))
def register(name, email, role):
    """Register a new user: <name> <email> <role>"""
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
    session = {'user_id': user_id, 'name': name, 'role': role}
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
#@click.option("--owner", default="teacher@example.com")
def upload(file, owner):
    """Upload a document (PDF or plaintext)"""
    ext = os.path.splitext(file)[1].lower()
    if ext not in ['.pdf', '.txt']:
        click.echo("Unsupported file type. Only .pdf and .txt are allowed.")
        return
    dest = os.path.join(DOCS_DIR, os.path.basename(file))
    os.replace(file, dest)
    save_metadata(os.path.basename(file), owner, ext)
    click.echo(f"Uploaded {dest} and metadata recorded.")


@cli.command()
@require_login
@click.argument("docname")
def summarize(docname):
    """Generate a summary via OpenAI"""
    client = OpenAI(
			# This is the default and can be omitted
			api_key=os.environ.get("OPENAI_API_KEY"),
		)
    
    path = os.path.join(DOCS_DIR, docname)
    if not os.path.exists(path):
        click.echo("Document not found.")
        return
    text = get_text(path)
    prompt = f"Summarize this for a teacher:\n\n{text}"
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
    )
    response = client.responses.create(
			model="gpt-4o-mini",
			input=prompt,
			#temperature=0.6,
			#max_tokens=1500
		)
    response_text = response.output_text
    click.echo(response_text)
    
	# Store the quiz in a file
    quiz_file = os.path.join(DOCS_DIR, f"{docname}_quiz.txt")
    with open(quiz_file, "w", encoding="utf-8") as f:
        f.write(response_text)
    click.echo(f"Quiz saved to {quiz_file}")
    


@cli.command()
@require_login
@require_role(['teacher','admin'])
@click.argument("response_file", type=click.Path(exists=True))
@click.argument("answer_key_file", type=click.Path(exists=True))
def grade(response_file, answer_key_file):
    """<response_file><answer_key_file> Grade quiz responses against the answer key locally"""
    # Parse answer key
    with open(answer_key_file, encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    #click.echo(f"lines: {lines}")
    # Locate 'Answer Key' section
    if '### Answer Key' in lines:
        start = lines.index('### Answer Key') + 1
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
def list_docs(session):
    """List uploaded documents"""
    conn = sqlite3.connect(DB_PATH)
    for row in conn.execute("SELECT id, name, owner, timestamp, type FROM documents"):
        click.echo(f"{row[0]} | {row[1]} | {row[2]} | {row[4]} @ {row[3]}")
    conn.close()


if __name__ == "__main__":
    cli()
