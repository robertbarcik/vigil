"""Tests for the OpenRouter client."""

import pytest

from vigil.client import VigilClient


def test_extract_content():
    response = {
        "choices": [
            {"message": {"content": "Hello world", "role": "assistant"}}
        ]
    }
    assert VigilClient.extract_content(response) == "Hello world"


def test_extract_content_empty():
    assert VigilClient.extract_content({}) == ""
    assert VigilClient.extract_content({"choices": []}) == ""


def test_client_init_with_key():
    client = VigilClient(api_key="test-key")
    assert client.api_key == "test-key"
