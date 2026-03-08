"""Tests for the OpenRouter client."""

import pytest

from vigil.client import VigilClient


class TestExtractContent:
    def test_normal_response(self):
        response = {
            "choices": [
                {"message": {"content": "Hello world", "role": "assistant"}}
            ]
        }
        assert VigilClient.extract_content(response) == "Hello world"

    def test_empty_response(self):
        assert VigilClient.extract_content({}) == ""

    def test_empty_choices(self):
        assert VigilClient.extract_content({"choices": []}) == ""

    def test_missing_content(self):
        response = {"choices": [{"message": {}}]}
        assert VigilClient.extract_content(response) == ""

    def test_multiline_content(self):
        response = {
            "choices": [
                {"message": {"content": "Line 1\nLine 2\nLine 3"}}
            ]
        }
        assert "Line 2" in VigilClient.extract_content(response)


class TestClientInit:
    def test_with_explicit_key(self):
        client = VigilClient(api_key="test-key")
        assert client.api_key == "test-key"

    def test_custom_base_url(self):
        client = VigilClient(api_key="k", base_url="http://localhost:8000")
        assert client.base_url == "http://localhost:8000"
