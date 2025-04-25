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

## Requirements

- Python ≥ 3.7  
- [pip](https://pip.pypa.io/)  
- **Environment variable**:  
  ```bash
  export OPENAI_API_KEY="sk-…"      # macOS / Linux
  $env:OPENAI_API_KEY="sk-…"        # PowerShell
