"""Validation tests for Table T02 Antigravity workspace skills, domain rules, and AGENTS.md catalog."""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_SKILLS: dict[str, list[str]] = {
    "t02-adk-bigquery": [
        "find_catalog_products",
        "get_storefront_performance",
        "get_audience_segments",
        "recommend_storefront_optimization",
        "ScalarQueryParameter",
    ],
    "t02-mcp-actions-a2a": [
        "publish_storefront_layout",
        "queue_visual_asset_render",
        "update_promo_banner",
        "sync_campaign_with_t01",
        "MCP_TOOLS",
        "STOREFRONT_TO_CAMPAIGN_SYNC",
    ],
    "t02-storefront-ui-multimodal": [
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "GEMINI_IMAGE_MODEL",
        "ui://storefront-preview/",
        "template.html",
    ],
    "t02-eval-and-deploy": [
        "golden.test.json",
        "make eval-validate PACK=t02",
        "cloudbuild.yaml",
        "make deploy",
        "make test-remote",
    ],
}


def _parse_frontmatter(md_text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter delimited by --- at the top of a SKILL.md file."""
    assert md_text.startswith("---\n"), "SKILL.md must begin with YAML frontmatter delimiter '---'"
    parts = md_text.split("---\n", 2)
    assert len(parts) == 3, "SKILL.md must contain closing YAML frontmatter delimiter '---'"
    meta = yaml.safe_load(parts[1])
    assert isinstance(meta, dict), "YAML frontmatter must parse to a mapping"
    return meta, parts[2]


def test_t02_domain_invariants_rule_exists() -> None:
    """Verify .agents/rules/t02-domain-invariants.md documents Table 2 invariants and guardrails."""
    rule_path = REPO_ROOT / ".agents" / "rules" / "t02-domain-invariants.md"
    assert rule_path.exists(), f"Missing domain rule file: {rule_path}"
    content = rule_path.read_text(encoding="utf-8")
    for required_token in (
        "t02_dynamic_storefronts",
        "30%",
        "SKU-0017",
        "GEMINI_MODEL",
        "GEMINI_IMAGE_MODEL",
        "MCP_TOOLS",
    ):
        assert required_token in content, f"Missing '{required_token}' in {rule_path.name}"


@pytest.mark.parametrize("skill_name,required_tokens", list(EXPECTED_SKILLS.items()))
def test_t02_antigravity_skills_structure_and_content(
    skill_name: str, required_tokens: list[str]
) -> None:
    """Verify each Table 2 Antigravity skill has valid YAML frontmatter and required tool references."""
    skill_file = REPO_ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
    assert skill_file.exists(), f"Missing Antigravity skill file: {skill_file}"

    raw_text = skill_file.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(raw_text)

    assert meta.get("name") == skill_name, (
        f"Frontmatter 'name' ({meta.get('name')!r}) must match directory '{skill_name}'"
    )
    description = meta.get("description", "")
    assert isinstance(description, str) and len(description.strip()) >= 40, (
        f"Skill '{skill_name}' must have a descriptive third-person 'description' in frontmatter"
    )

    for token in required_tokens:
        assert token in body, f"Skill '{skill_name}' body is missing required reference '{token}'"


def test_agents_md_documents_t02_skills_and_architecture() -> None:
    """Verify AGENTS.md indexes Table 2 tools, BigQuery tables, and .agents/skills/."""
    agents_md = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for expected in (
        "t02_dynamic_storefronts",
        "t02-adk-bigquery",
        "t02-mcp-actions-a2a",
        "t02-storefront-ui-multimodal",
        "t02-eval-and-deploy",
        "recommend_storefront_optimization",
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "sync_campaign_with_t01",
    ):
        assert expected in agents_md, f"AGENTS.md is missing reference to '{expected}'"
