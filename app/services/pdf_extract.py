from pypdf import PdfReader


def extract_text_with_pypdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    parts: list[str] = []

    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        parts.append(f"\n--- PAGE {i} ---\n{text}")

    return "\n".join(parts)