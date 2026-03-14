from concurrent import futures
import grpc
import pickle
from pathlib import Path

import kvstore_pb2
import kvstore_pb2_grpc

SERVER_NAME = "personal-school-kvstore"
SERVER_VERSION = "1.0.0"
SERVER_ADDRESS = "localhost:50051"
STATE_FILE = Path(__file__).resolve().with_name("kvstore_state.pkl")

class KVStore(kvstore_pb2_grpc.KeyValueStoreServicer):
    def __init__(self):
        self.textbook_chunks: dict[str, str] = {}
        self.embeddings: dict[str, bytes] = {}
        self.load_state()


    def load_state(self):
        if not STATE_FILE.exists():
            return

        with STATE_FILE.open("rb") as state_file:
            state = pickle.load(state_file)

        self.textbook_chunks = dict(state.get("textbook_chunks", {}))
        self.embeddings = dict(state.get("embeddings", {}))
        print(f"Loaded {len(self.textbook_chunks)} records from {STATE_FILE}")


    def save_state(self):
        state = {
            "textbook_chunks": self.textbook_chunks,
            "embeddings": self.embeddings,
        }

        with STATE_FILE.open("wb") as state_file:
            pickle.dump(state, state_file)


    def Put(self, request, context):
        overwritten = request.key in self.textbook_chunks or request.key in self.embeddings
        self.textbook_chunks[request.key] = request.textbook_chunk
        self.embeddings[request.key] = request.embedding
        return kvstore_pb2.PutResponse(overwritten=overwritten)


    def StreamEmbeddings(self, request, context):
        items = list(self.embeddings.items())

        for key, embedding in items:
            yield kvstore_pb2.StreamEmbeddingsResponse(key=key, embedding=embedding)


    def GetText(self, request, context):
        textbook_chunk = self.textbook_chunks.get(request.key)

        if textbook_chunk is None:
            return kvstore_pb2.GetTextResponse(found=False)

        return kvstore_pb2.GetTextResponse(found=True, textbook_chunk=textbook_chunk)


    def Health(self, request, context):
        key_count = len(self.textbook_chunks)

        return kvstore_pb2.HealthResponse(
            name=SERVER_NAME,
            version=SERVER_VERSION,
            key_count=key_count,
        )


def serve(address: str = SERVER_ADDRESS) -> None:
    kv_store = KVStore()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
    kvstore_pb2_grpc.add_KeyValueStoreServicer_to_server(kv_store, server)
    server.add_insecure_port(address)
    server.start()

    print(f"KV store server listening on {address}")
    try:
        server.wait_for_termination()
    finally:
        kv_store.save_state()

if __name__ == "__main__":
    serve()
