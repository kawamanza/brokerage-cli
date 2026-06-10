import json

import yaml

from brokerage.models import BrokerageFile, BrokerInfo, OutputFormat
from brokerage.serializers import serialize_payload


def test_serializes_json_and_yaml():
    parsed_file = BrokerageFile(broker=BrokerInfo(name="Clear"), source_file="sample.pdf", pages=1)

    as_json = serialize_payload(parsed_file, OutputFormat.JSON)
    as_yaml = serialize_payload(parsed_file, OutputFormat.YAML)

    assert json.loads(as_json)["broker"]["name"] == "Clear"
    assert yaml.safe_load(as_yaml)["source_file"] == "sample.pdf"


def test_compact_output_removes_empty_and_zero_values_by_default():
    payload = {
        "keep": "value",
        "empty_string": "",
        "empty_list": [],
        "empty_dict": {},
        "none": None,
        "zero": "0.00",
        "nested": {"keep": "1.23", "zero": "0.00"},
    }

    data = json.loads(serialize_payload(payload, OutputFormat.JSON))

    assert data == {"keep": "value", "nested": {"keep": "1.23"}}


def test_verbose_output_keeps_empty_and_zero_values():
    payload = {"keep": "value", "empty": None, "zero": "0.00"}

    data = json.loads(serialize_payload(payload, OutputFormat.JSON, compact=False))

    assert data == payload
