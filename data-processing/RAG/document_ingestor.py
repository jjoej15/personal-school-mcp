import json
import re
from pathlib import Path
from typing import Dict, Iterable, List

from sentence_transformers import SentenceTransformer

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

OUTPUT_FILE = "chunks_embeddings.jsonl"
EMBEDDINGS_PATH = Path(__file__).resolve().parent / "embeddings"
DOCUMENTS_PATH = Path(__file__).resolve().parent / "documents"

CHUNK_MAX_WORDS = 220 # length of text chunks to embed
CHUNK_OVERLAP_PARAGRAPHS = 1
BATCH_SIZE = 32 # embedding text size

def discover_documents(documents_dir: Path) -> List[Path]:
	files = [
		path
		for path in documents_dir.rglob("*")
		if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
	]
	return sorted(files)


def normalize_paragraph(text: str) -> str:
	text = text.replace("\u00a0", " ")
	text = re.sub(r"\s+", " ", text)
	return text.strip()


def extract_pdf_paragraphs(file_path: Path) -> List[str]:
	from pypdf import PdfReader
	reader = PdfReader(str(file_path))
	# pdf text extraction is page-based, so join pages first then recover paragraph breaks
	joined = "\n\n".join(page.extract_text() or "" for page in reader.pages)
	raw_parts = re.split(r"\n\s*\n", joined)
	return [normalize_paragraph(part) for part in raw_parts]


def extract_docx_paragraphs(file_path: Path) -> List[str]:
	from docx import Document
	doc = Document(str(file_path))
	return [normalize_paragraph(p.text) for p in doc.paragraphs]


def extract_paragraphs(file_path: Path) -> List[str]:
	suffix = file_path.suffix.lower()
	if suffix == ".pdf":
		paragraphs = extract_pdf_paragraphs(file_path)
	else:
		paragraphs = extract_docx_paragraphs(file_path)
	return paragraphs


def chunk_paragraphs(
	paragraphs: List[str], 
	max_words: int = CHUNK_MAX_WORDS, 
	overlap_paragraphs: int = CHUNK_OVERLAP_PARAGRAPHS,
) -> List[str]:
	if not paragraphs:
		return []

	chunks: List[str] = []
	chunk_buffer: List[str] = []
	chunk_word_count = 0

	for paragraph in paragraphs:
		words = len(paragraph.split())

		# keep very large paragraphs by themselves
		if words >= max_words:
			if chunk_buffer:
				chunks.append("\n\n".join(chunk_buffer))
			chunks.append(paragraph)
			chunk_buffer = []
			chunk_word_count = 0
			continue

		if chunk_word_count + words > max_words and chunk_buffer:
			chunks.append("\n\n".join(chunk_buffer))
			# retain trailing paragraphs to preserve local context across neighboring chunks
			chunk_buffer = chunk_buffer[-overlap_paragraphs:] if overlap_paragraphs > 0 else []
			chunk_word_count = sum(len(p.split()) for p in chunk_buffer)

		chunk_buffer.append(paragraph)
		chunk_word_count += words

	if chunk_buffer:
		chunks.append("\n\n".join(chunk_buffer))

	return chunks


def build_records(file_path: Path, chunks: Iterable[str]) -> List[Dict[str, object]]:
	records: List[Dict[str, object]] = []
	for i, chunk in enumerate(chunks):
		records.append(
			{
				"id": f"{file_path.stem}-{i}",
				"source_file": file_path.name,
				"text": chunk,
			}
		)
	return records


def embed_records(
	records: List[Dict[str, object]],
	model_name: str = MODEL_NAME,
	batch_size: int = BATCH_SIZE,
) -> List[Dict[str, object]]:
	if not records:
		return records

	model = SentenceTransformer(model_name)
	texts: List[str] = [str(record["text"]) for record in records]
	vectors = model.encode(
		texts,
		batch_size=batch_size,
		show_progress_bar=True,
		convert_to_numpy=True,
		normalize_embeddings=True,
	)

	for record, vector in zip(records, vectors):
		record["embedding"] = vector.tolist()

	return records


def write_jsonl(records: Iterable[Dict[str, object]], output_path: Path) -> None:
	output_path.parent.mkdir(parents=True, exist_ok=True)
	with output_path.open("w", encoding="utf-8") as out_file:
		for record in records:
			out_file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main():
	documents_dir = DOCUMENTS_PATH
	output_path = EMBEDDINGS_PATH / OUTPUT_FILE

	source_files = discover_documents(documents_dir)
	if not source_files:
		print(f"No .pdf or .docx files found in: {documents_dir}")
		return

	all_records: List[Dict[str, object]] = []
	for file_path in source_files:
		paragraphs = extract_paragraphs(file_path)
		chunks = chunk_paragraphs(paragraphs)
		all_records.extend(build_records(file_path, chunks))

	embedded_records = embed_records(all_records)
	write_jsonl(embedded_records, output_path)

	print(f"Processed files: {len(source_files)}")
	print(f"Total chunks: {len(embedded_records)}")
	print(f"Output JSONL: {output_path}")

if __name__ == "__main__":
	main()
