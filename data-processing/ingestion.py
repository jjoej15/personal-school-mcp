import json
from array import array
from pathlib import Path
import grpc

import kvstore_pb2
import kvstore_pb2_grpc

SERVER_ADDRESS = "localhost:50051"
EMBEDDINGS_JSONL = Path(__file__).resolve().parents[1] / "data-processing" / "RAG" / "embeddings" / "chunks_embeddings.jsonl"

def load_embedding_records(jsonl_path: Path) -> list[dict[str, object]]:
	records: list[dict[str, object]] = []
	with jsonl_path.open("r", encoding="utf-8") as jsonl_file:
		for line in jsonl_file:
			if not line.strip():
				continue
			records.append(json.loads(line))
	return records


def serialize_embedding(embedding: object) -> bytes:
	if not isinstance(embedding, list):
		raise TypeError("embedding must be a list of floats")

	# pack embeddings as float32 bytes to keep the rpc payload compact.
	return array("f", (float(value) for value in embedding)).tobytes()


def main():
	if not EMBEDDINGS_JSONL.exists():
		raise FileNotFoundError(f"Embeddings file not found: {EMBEDDINGS_JSONL}")

	records = load_embedding_records(EMBEDDINGS_JSONL)
	if not records:
		print(f"No records found in {EMBEDDINGS_JSONL}")
		return

	with grpc.insecure_channel(SERVER_ADDRESS) as channel:
		stub = kvstore_pb2_grpc.KeyValueStoreStub(channel)
		health = stub.Health(kvstore_pb2.HealthRequest())
		print(
			f"Connected to {health.name} v{health.version} with {health.key_count} existing keys"
		)

		overwritten_count = 0
		for record in records:
			response = stub.Put(
				kvstore_pb2.PutRequest(
					key=str(record["id"]),
					textbook_chunk=str(record["text"]),
					embedding=serialize_embedding(record["embedding"]),
				)
			)
			overwritten_count += int(response.overwritten)

	print(f"Uploaded records: {len(records)}")
	print(f"Overwritten keys: {overwritten_count}")

if __name__ == "__main__":
	main()
