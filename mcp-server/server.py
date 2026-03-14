from pathlib import Path
from fastmcp import FastMCP
import grpc
import numpy as np
from sentence_transformers import SentenceTransformer

import kvstore_pb2
import kvstore_pb2_grpc

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTO_MODULE_DIR = PROJECT_ROOT / "grpc_kvs" / "src" / "kvstore"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SERVER_ADDRESS = "localhost:50051"

mcp = FastMCP("Personal School MCP Server")
embedding_model = SentenceTransformer(MODEL_NAME)

def deserialize_embedding(embedding_bytes: bytes) -> np.ndarray:
    return np.frombuffer(embedding_bytes, dtype=np.float32)


@mcp.tool
def search_lecture_slides(query: str, top_k: int = 5) -> list[dict[str, object]]:
    """
    Retrieves the most relevant lecture slide passages for a query using semantic similarity.
    Call this tool when a user's question requires information from the course text,
    and use the returned passages as context for your response.
    """
    if not query.strip():
        raise ValueError("query must not be empty")

    if top_k <= 0:
        raise ValueError("top_k must be greater than 0")

    query_embedding = embedding_model.encode(
        query,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    ranked_matches: list[tuple[float, str]] = []

    try:
        with grpc.insecure_channel(SERVER_ADDRESS) as channel:
            stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)

            for item in stub.StreamEmbeddings(kvstore_pb2.StreamEmbeddingsRequest()):
                candidate_embedding = deserialize_embedding(item.embedding)
                score = float(np.dot(query_embedding, candidate_embedding))
                ranked_matches.append((score, item.key))

            if not ranked_matches:
                return []

            ranked_matches.sort(key=lambda match: match[0], reverse=True)
            top_matches = ranked_matches[:top_k]

            passages: list[dict[str, object]] = []
            for score, key in top_matches:
                response = stub.GetText(kvstore_pb2.GetTextRequest(key=key))
                if not response.found:
                    continue

                passages.append(
                    {
                        "key": key,
                        "score": score,
                        "text": response.textbook_chunk,
                    }
                )
    except grpc.RpcError as exc:
        raise RuntimeError("could not reach the local kv store server") from exc

    return passages

if __name__ == "__main__":
    mcp.run()
