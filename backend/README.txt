Run from the project root. See ../README.md for Windows and macOS setup and launch instructions.

Manual backend launch from the project root:

Windows:
.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8002

macOS:
.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8002
