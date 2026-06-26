from pathlib import Path
from collections.abc import Sequence

from app.schemas.transaction import ParsedTransactionsResponse
from app.services.llm_client import make_openai_strict_schema, openai_chat_json


MAX_MODEL_INPUT_CHARS = 12000


def build_prompt(raw_text: str, categories: Sequence[tuple[int, str]]) -> str:
    template = Path("app/prompts/parse_transactions.txt").read_text(encoding="utf-8")

    cleaned_text = raw_text.strip()
    clipped_text = cleaned_text[:MAX_MODEL_INPUT_CHARS]
    category_lines = "\n".join(
        f"- {category_id}: {name}" for category_id, name in categories
    )

    return f"""{template}

REQUIRED JSON FIELDS FOR EACH TRANSACTION OBJECT:
- booking_date
- amount
- currency
- direction
- counterparty
- raw_description
- normalized_description
- category_id
- confidence

ALLOWED CATEGORIES WITH IDS:
{category_lines}

RAW BANK STATEMENT TEXT:
{clipped_text}
"""


async def parse_transactions_from_text(
    raw_text: str,
    categories: Sequence[tuple[int, str]],
) -> ParsedTransactionsResponse:
    raw_schema = ParsedTransactionsResponse.model_json_schema()
    schema = make_openai_strict_schema(raw_schema)

    prompt = build_prompt(raw_text, categories=categories)
    result = await openai_chat_json(prompt, schema=schema)

    parsed = ParsedTransactionsResponse.model_validate_json(result["content"])
    return parsed
