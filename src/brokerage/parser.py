from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Protocol, runtime_checkable

import brokerage.brokers
from brokerage.errors import UnsupportedBrokerError
from brokerage.models import BrokerageFile, ExtractedPdf


@runtime_checkable
class BrokerageParser(Protocol):
    def matches(self, text: str) -> bool: ...

    def parse(self, extracted: ExtractedPdf) -> BrokerageFile: ...


def _is_parser_class(candidate: type) -> bool:
    return callable(getattr(candidate, "matches", None)) and callable(getattr(candidate, "parse", None))


def discover_parsers() -> list[BrokerageParser]:
    parsers: list[BrokerageParser] = []
    for module_info in sorted(pkgutil.iter_modules(brokerage.brokers.__path__), key=lambda item: item.name):
        if module_info.ispkg or module_info.name.startswith("_"):
            continue

        module = importlib.import_module(f"{brokerage.brokers.__name__}.{module_info.name}")
        for _, parser_class in inspect.getmembers(module, inspect.isclass):
            if parser_class.__module__ != module.__name__:
                continue
            if not parser_class.__name__.endswith("Parser"):
                continue
            if not _is_parser_class(parser_class):
                continue
            parsers.append(parser_class())
    return parsers


PARSERS = discover_parsers()


def parse_note(extracted: ExtractedPdf) -> BrokerageFile:
    for parser in PARSERS:
        if parser.matches(extracted.text):
            return parser.parse(extracted)

    raise UnsupportedBrokerError("Unable to identify brokerage note parser.")
