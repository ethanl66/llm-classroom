# doccli

A simple command-line Document Analyzer for teachers and students.
Leverages OpenAI to automatically summarize documents, generate quizzes & answer keys, grade student responses, and manage materials via SQLite.

---

## Features

- **User Authentication & Roles**  
  - `admin`, `teacher`, `student` roles  
  - Only admins can create teacher/admin accounts  
  - Teachers & admins can upload, quiz, grade, and delete documents  
  - Students can self-register, summarize documents, and access reading materials/quizzes.

- **Document Management**  
  - Upload PDF & plain-text (`.txt`) files  
  - Metadata stored in `metadata.db` (SQLite)  
  - Readings copied to `docs/` directory
  - Quizzes, answer keys, and student responses stored in respective directories

- **LLM-Powered Services**  
  - **Summarize** any document via `summarize` command  
  - **Quiz Generation**: multiple-choice quizzes + answer keys  

- **File Organization**  
  - `docs/` &mdash; uploaded reading materials  
  - `quizzes/` &mdash; generated quizzes  
  - `answer_keys/` &mdash; generated answer keys  
  - `student_responses/` &mdash; place student response files here  

- **Convenience**  
  - `list-docs`, `list-quizzes`, `read-quiz`, `delete-doc`  
  - Context-aware `--help` that only shows your permitted commands  
  - Configurable help width for long descriptions  

---

## Installation
1) Clone and Install<br>
   ```
   git clone https://github.com/ethanl66/llm-classroom.git
   cd llm-classroom
   pip install --upgrade pip setuptools wheel
   pip install -e .
   ```
   Run `doccli --help`

---

## Usage
All commands enfore login/session state and role permissions.
- **Account Management**
  ```
  # Public self-register as a student
  $ doccli register "Alice Student" alice@school.com student
  
  # Admins (already logged in) can create teacher accounts:
  $ doccli register "Bob Teacher" bob@school.com teacher
  
  # Log in & out
  $ doccli login alice@school.com
  $ doccli logout
  ```
- **Document Workflows**
  ```
  # Upload (teacher/admin only)
  $ doccli upload syllabus.pdf
  
  # Summarize (any logged-in user)
  $ doccli summarize syllabus.pdf
  
  # Generate a quiz + answer key (teacher/admin only)
  $ doccli quiz syllabus.pdf --n 5
  
  # List uploaded docs
  $ doccli list-docs
  
  # List quizzes
  $ doccli list-quizzes
  
  # View a quiz
  $ doccli read-quiz syllabus_quiz.txt
  
  # Grade student responses (teacher/admin only)
  $ # put responses.txt in student_responses/
  $ doccli grade responses.txt syllabus_answer_key.txt
  
  # Delete a document by name (teacher/admin only)
  $ doccli delete-doc syllabus.pdf
  ```

---

## Requirements

- Python ≥ 3.7  
- [pip](https://pip.pypa.io/)  
- **Environment variable**:  
  ```bash
  export OPENAI_API_KEY="sk-…"      # macOS / Linux
  $env:OPENAI_API_KEY="sk-…"        # PowerShell
