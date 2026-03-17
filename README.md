# personal-school-mcp

RAG + MCP server project that connects AI agents to a user's Canvas account, Google Calendar, and a local gRPC key-value store that holds lecture slide embeddings. Allows user to ask an AI assistant personalized questions about course schedules, assignments, and lecture content using 6 MCP tools.

Extended write-up: https://joejanderson.dev/projects/mcp-project

What was implemented:

- A document ingestion pipeline that reads `.pdf` and `.docx` lecture material, normalizes text, chunks content, generates embeddings, and writes JSONL records.
- A gRPC key-value server that stores lecture text chunks and embeddings, supports health checks, streams embeddings for retrieval, and persists state to disk.
- An ingestion client that loads generated embeddings and uploads them into the KV store.
- Lecture search tools that perform semantic retrieval by comparing query embeddings against stored vectors and returning top matching passages.
- Canvas MCP tools for listing and filtering assignments, fetching assignment details, and retrieving grade/submission information.
- Google Calendar MCP tools for listing calendars and retrieving events across day, week, and custom date windows.
- A FastMCP server that registers all tools and provides one local MCP endpoint for AI assistants.
- Devcontainer and dependency setup so the full system can be reproduced consistently.

## Usage Guide

Follow these steps in order.

### 1) Start the devcontainer

This project is configured for VS Code Dev Containers in `.devcontainer/devcontainer.json`.

1. Open the folder in VS Code.
2. Run: Rebuild and Reopen in Container.
3. Wait for `postCreateCommand` to finish installing dependencies from `requirements.txt`.

### 2) Add PDF/DOCX documents (on first time usage only)

Place your lecture files in:

- `data-processing/RAG/documents/`

Supported file types:

- `.pdf`
- `.docx`

### 3) Run the document ingestor (on first time usage only)

From the workspace root, run:

```bash
python data-processing/RAG/document_ingestor.py
```

This will:

- Read documents from `data-processing/RAG/documents/`
- Chunk the text
- Create embeddings with `sentence-transformers/all-MiniLM-L6-v2`
- Write output to `data-processing/RAG/embeddings/chunks_embeddings.jsonl`

### 4) Start the KV server

In terminal 1:

```bash
python kv-server/server.py
```

### 5) Run ingestion into KV store (on first time usage only)

In terminal 2 (keep terminal 1 running):

```bash
python data-processing/ingestion.py
```

This uploads chunk text + embedding bytes into the KV server.

### 6) Update `.env` (on first time usage only)

Create your env file from the template:

```bash
cp .env.example .env
```

Then edit `.env` and set the environment variables listed in `.env.example`

Notes:

- `credentials.json` should be your OAuth client credentials from Google Cloud.
- `token.json` is created/updated after first successful auth.
- Keep `.env`, `credentials.json`, and `token.json` out of version control.

### 7) Run the MCP server

You can start it directly:

```bash
python mcp-server/server.py
```

Or use the MCP config in `.vscode/mcp.json`, which points to:

- Command: `python`
- Args: `${workspaceFolder}/mcp-server/server.py`

### 8.) Use the MCP server

Using GitHub Copilot Chat, you can now use the below MCP tools:
- `search_lecture_slides`: Retrieves the most relevant lecture slide passages for a query using semantic similarity.
- `canvas_get_schedule`: Returns Canvas calendar events for a date range.
- `canvas_get_assignments`: Returns Canvas assignments by due-date window.
- `canvas_get_assignment_details`: Returns assignment details for a specific assignment name.
- `google_calendar_list_calendars`: Returns all calendars available to the authenticated user.
- `google_calendar_get_events`: Returns Google Calendar events by time window.

You can also use the `.github/agents/personal-agent.agent.md` agent in this workspace and ask questions about Canvas schedules, assignments, assignment grades, Google Calendar events, or lecture content.

## Typical terminal layout

- Terminal 1: `python kv-server/server.py`
- Terminal 2: `python mcp-server/server.py`
- Terminal 3 (one-time when data changes):
	- `python data-processing/RAG/document_ingestor.py`
	- `python data-processing/ingestion.py`
