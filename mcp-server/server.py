from pathlib import Path

from fastmcp import FastMCP
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from canvas_tools import register_canvas_tools
from lecture_tools import register_lecture_slide_tools

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SERVER_ADDRESS = "localhost:50051"

load_dotenv(PROJECT_ROOT / ".env")

mcp = FastMCP("Personal School MCP Server")
embedding_model = SentenceTransformer(MODEL_NAME)

register_lecture_slide_tools(mcp, embedding_model, SERVER_ADDRESS)
register_canvas_tools(mcp)

if __name__ == "__main__":
    mcp.run()
