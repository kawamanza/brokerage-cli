from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import yaml
from pydantic import BaseModel

from brokerage.models import OutputFormat


def serialize_payload(
    payload: BaseModel | dict[str, Any],
    output: OutputFormat,
    *,
    compact: bool = True,
) -> str:
    if isinstance(payload, BaseModel):
        data = payload.model_dump(mode="json")
    else:
        data = payload

    if compact:
        data = compact_payload(data)

    if output == OutputFormat.JSON:
        return json.dumps(data, ensure_ascii=False, indent=2)

    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def compact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            compacted_item = compact_payload(item)
            if _should_keep(compacted_item):
                compacted[key] = compacted_item
        return compacted

    if isinstance(value, list):
        return [item for item in (compact_payload(item) for item in value) if _should_keep(item)]

    return value


def _should_keep(value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return False
    if value in (0, 0.0, Decimal("0")):
        return False
    if isinstance(value, str) and value in {"0", "0.0", "0.00", "0.00000000"}:
        return False
    return True
