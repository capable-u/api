import httpx
from app.core.config import settings


class LLMClientError(RuntimeError):
    pass


def make_openai_strict_schema(schema: dict) -> dict:
    """Adapts a Pydantic JSON Schema to OpenAI Structured Outputs format."""

    def transform(node: dict) -> dict:
        if not isinstance(node, dict):
            return node
        for key, value in list(node.items()):
            if isinstance(value, dict):
                node[key] = transform(value)
            elif isinstance(value, list):
                node[key] = [
                    transform(item) if isinstance(item, dict) else item
                    for item in value
                ]
        if node.get("type") == "object" and "properties" in node:
            props = node["properties"]
            node["required"] = list(props.keys())
            node["additionalProperties"] = False
        return node

    return transform(schema)


async def openai_chat_json(prompt: str, schema: dict) -> dict:
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract bank transactions from German bank statement text. "
                    "Return only valid JSON matching the provided schema."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "parsed_transactions",
                "strict": True,
                "schema": schema,
            },
        },
        "temperature": 0,
    }

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.openai_base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
    except httpx.HTTPError as e:
        raise LLMClientError(f"OpenAI request failed: {e}") from e

    if response.status_code >= 400:
        raise LLMClientError(f"OpenAI error {response.status_code}: {response.text}")

    data = response.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMClientError(f"Unexpected OpenAI response shape: {data}") from e

    if not content:
        raise LLMClientError(f"Empty model response: {data}")

    return {
        "raw": data,
        "content": content,
    }
