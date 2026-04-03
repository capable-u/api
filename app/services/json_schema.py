def make_openai_strict_schema(schema: dict) -> dict:
    """
    Recursively adapts a Pydantic-generated JSON Schema
    to the stricter format expected by OpenAI Structured Outputs.
    """

    def transform(node: dict) -> dict:
        if not isinstance(node, dict):
            return node

        # Recurse first
        for key, value in list(node.items()):
            if isinstance(value, dict):
                node[key] = transform(value)
            elif isinstance(value, list):
                node[key] = [
                    transform(item) if isinstance(item, dict) else item
                    for item in value
                ]

        # For object schemas:
        if node.get("type") == "object" and "properties" in node:
            props = node["properties"]
            node["required"] = list(props.keys())
            node["additionalProperties"] = False

        return node

    return transform(schema)
