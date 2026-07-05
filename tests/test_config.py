"""Tests for configuration loading."""

import pytest
from pathlib import Path

from vigil.config import load_behaviors, load_eu_ai_act, load_config, get_vigil_dir


class TestBehaviors:
    def test_load_behaviors(self):
        behaviors = load_behaviors()
        assert len(behaviors) == 12
        assert "prompt-injection" in behaviors
        assert "social-engineering-assistance" in behaviors

    def test_behavior_has_required_fields(self):
        behaviors = load_behaviors()
        for key, behavior in behaviors.items():
            assert behavior.name, f"{key} missing name"
            assert behavior.description, f"{key} missing description"
            assert behavior.category in ("security", "safety", "compliance"), f"{key} invalid category"
            assert behavior.severity in ("low", "medium", "high", "critical"), f"{key} invalid severity"

    def test_all_behaviors_have_strategies(self):
        behaviors = load_behaviors()
        for key, behavior in behaviors.items():
            assert len(behavior.attack_strategies) > 0, f"{key} has no attack strategies"

    def test_all_behaviors_have_eu_ai_act(self):
        behaviors = load_behaviors()
        for key, behavior in behaviors.items():
            assert len(behavior.eu_ai_act_articles) > 0, f"{key} has no EU AI Act mapping"


class TestEuAiAct:
    def test_load_mapping(self):
        mapping = load_eu_ai_act()
        assert "articles" in mapping
        assert len(mapping["articles"]) > 0

    def test_articles_have_required_fields(self):
        mapping = load_eu_ai_act()
        for article_name, article in mapping["articles"].items():
            assert "summary" in article, f"{article_name} missing summary"
            assert "testable_behaviors" in article, f"{article_name} missing testable_behaviors"
            assert len(article["testable_behaviors"]) > 0

    def test_mapped_behaviors_exist(self):
        mapping = load_eu_ai_act()
        behaviors = load_behaviors()
        for article_name, article in mapping["articles"].items():
            for behavior in article["testable_behaviors"]:
                assert behavior in behaviors, f"Article '{article_name}' references unknown behavior '{behavior}'"


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path):
        config_path = tmp_path / "test.yaml"
        config_path.write_text(
            "behavior: prompt-injection\n"
            "target_model: test/model\n"
            "num_scenarios: 2\n"
            "min_turns: 4\n"
            "attacker_persistence: medium\n"
        )
        config = load_config(config_path)
        assert config.behavior == "prompt-injection"
        assert config.target_model == "test/model"
        assert config.num_scenarios == 2
        assert config.min_turns == 4
        assert config.attacker_persistence == "medium"

    def test_load_fills_defaults(self, tmp_path):
        config_path = tmp_path / "minimal.yaml"
        config_path.write_text(
            "behavior: test\n"
            "target_model: test/model\n"
        )
        config = load_config(config_path)
        assert config.attacker_model == "qwen/qwen3-235b-a22b"
        assert config.num_turns == 10
        assert config.min_turns == 3


class TestVigilDir:
    def test_get_vigil_dir(self, vigil_temp_dir):
        d = get_vigil_dir()
        assert d.exists()
        assert str(d) == str(vigil_temp_dir)
