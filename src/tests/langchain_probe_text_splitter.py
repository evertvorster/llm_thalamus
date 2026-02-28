# src/tests/langchain_probe_text_splitter.py
from langchain_text_splitters import RecursiveCharacterTextSplitter

def main() -> int:
    text = "A" * 1200 + "\n\n" + "B" * 1200 + "\n\n" + "C" * 1200

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=80,
    )

    chunks = splitter.split_text(text)
    print("chunks:", len(chunks))
    for i, c in enumerate(chunks[:3]):
        print(f"\n--- chunk {i} len={len(c)} ---")
        print(c[:120] + " ...")

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
