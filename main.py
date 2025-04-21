#!/usr/bin/env python3
import os
import sqlite3
import datetime
import click
from openai import OpenAI

# PDF text extraction
from pdfminer.high_level import extract_text

# ——— Configuration ———
DB_PATH = "metadata.db"
DOCS_DIR = "docs/"

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
    conn.commit()
    conn.close()


def save_metadata(name, owner, doc_type):
    conn = sqlite3.connect(DB_PATH)
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


# ——— CLI Commands ———
@click.group()
def cli():
    """Document Analyzer CLI"""
    os.makedirs(DOCS_DIR, exist_ok=True)
    init_db()


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--owner", default="teacher@example.com")
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
@click.argument("docname")
@click.option("--n", default=5, help="Number of quiz questions")
def quiz(docname, n):
    """Auto‑generate a quiz"""
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
def list_docs():
    """List uploaded documents"""
    conn = sqlite3.connect(DB_PATH)
    for row in conn.execute("SELECT id, name, owner, timestamp, type FROM documents"):
        click.echo(f"{row[0]} | {row[1]} | {row[2]} | {row[4]} @ {row[3]}")
    conn.close()


if __name__ == "__main__":
    cli()
