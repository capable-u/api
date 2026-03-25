from pathlib import Path

from app.schemas.transaction import ParsedTransactionsResponse
from app.services.llm_client import openai_chat_json
from app.services.json_schema import make_openai_strict_schema


MAX_MODEL_INPUT_CHARS = 12000


def build_prompt(raw_text: str) -> str:
    template = Path("app/prompts/parse_transactions.txt").read_text(encoding="utf-8")

    cleaned_text = raw_text.strip()
    clipped_text = cleaned_text[:MAX_MODEL_INPUT_CHARS]

    return f"""{template}

RAW BANK STATEMENT TEXT:
{clipped_text}
"""


async def parse_transactions_from_text(raw_text: str) -> ParsedTransactionsResponse:
    raw_schema = ParsedTransactionsResponse.model_json_schema()
    schema = make_openai_strict_schema(raw_schema)

    prompt = build_prompt(raw_text)
    result = await openai_chat_json(prompt, schema=schema)

    parsed = ParsedTransactionsResponse.model_validate_json(result["content"])
    return parsed