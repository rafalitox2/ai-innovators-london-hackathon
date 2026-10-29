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
    "t02-worktree-collab": [
        "make worktree",
        "make worktree-link",
        "make verify",
        "git worktree",
        "pull_request_template.md",
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
        "t02-worktree-collab",
        "recommend_storefront_optimization",
        "generate_hero_lifestyle_image",
        "render_storefront_preview",
        "sync_campaign_with_t01",
    ):
        assert expected in agents_md, f"AGENTS.md is missing reference to '{expected}'"


def test_github_ci_workflow_triggers_on_all_branches_pr_and_manual_dispatch() -> None:
    """Verify .github/workflows/ci.yml triggers on all branch pushes, PRs, and workflow_dispatch."""
    ci_path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci_path.exists(), "Missing .github/workflows/ci.yml"
    ci_data = yaml.safe_load(ci_path.read_text(encoding="utf-8"))
    triggers = ci_data.get("on") or ci_data.get(True)
    assert isinstance(triggers, dict), "ci.yml 'on' section must be a mapping"
    assert "pull_request" in triggers, "ci.yml must trigger on pull_request"
    assert "push" in triggers, "ci.yml must trigger on push"
    assert "workflow_dispatch" in triggers, "ci.yml must enable manual workflow_dispatch trigger"
    push_branches = triggers["push"].get("branches", [])
    assert "**" in push_branches, "ci.yml push trigger must cover all branches ('**')"


def test_makefile_and_gitignore_support_parallel_worktrees() -> None:
    """Verify Makefile and .gitignore support multi-person and multi-agent git worktrees."""
    gitignore_lines = [
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    ]
    assert ".venv" in gitignore_lines, ".gitignore must ignore symlinked .venv in worktrees"
    assert ".venv/" in gitignore_lines, ".gitignore must ignore .venv/ directory"

    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    for required_target in (
        "MAIN_WORKTREE",
        "worktree:",
        "worktree-link:",
        "worktree-list:",
        "verify:",
    ):
        assert required_target in makefile, f"Makefile is missing '{required_target}' for worktree setup"


def test_docs_logbook_and_specs_align_with_all_prs() -> None:
    """Verify docs/ logbook and phase specs exist and cover PRs #7..#16 and worktree workflows."""
    for doc_name in (
        "README.md",
        "BITACORA_T02.md",
        "PHASE1_SPEC.md",
        "PHASE2_SPEC.md",
        "PHASE3_SPEC.md",
        "PITCH_T02.md",
    ):
        doc_path = REPO_ROOT / "docs" / doc_name
        assert doc_path.exists(), f"Missing documentation file: {doc_path}"

    bitacora = (REPO_ROOT / "docs" / "BITACORA_T02.md").read_text(encoding="utf-8")
    for expected_token in (
        "#7",
        "#8",
        "#9",
        "#10",
        "#11",
        "#12",
        "#13",
        "#14",
        "#15",
        "#16",
        "#17",
        "before_tool_security_callback",
        "make worktree",
        "make verify",
    ):
        assert expected_token in bitacora, f"BITACORA_T02.md is missing '{expected_token}'"


def test_repository_cleaned_to_t02_challenge_and_official_docs() -> None:
    """Verify non-T02 challenges (T03..T10) are removed and only official + T02 docs remain."""
    challenges_dir = REPO_ROOT / "challenges"
    challenge_files = sorted(p.name for p in challenges_dir.glob("*.md"))
    assert challenge_files == [
        "README.md",
        "T02-dynamic_storefronts.md",
    ], f"challenges/ should only contain README.md and T02-dynamic_storefronts.md, found: {challenge_files}"

    seed_packs_dir = REPO_ROOT / "seed_packs"
    pack_dirs = sorted(
        p.name
        for p in seed_packs_dir.iterdir()
        if p.is_dir() and not p.name.startswith("__")
    )
    assert pack_dirs == [
        "t00_example",
        "t01_campaign_orchestrator",
        "t02_dynamic_storefronts",
    ], f"seed_packs/ should only retain t00_example, t01_campaign_orchestrator (A2A), and t02_dynamic_storefronts, found: {pack_dirs}"

    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SEED_PACK=t02" in env_example, ".env.example must default to SEED_PACK=t02"

    docs_dir = REPO_ROOT / "docs"
    doc_md_files = sorted(p.name for p in docs_dir.glob("*.md"))
    assert doc_md_files == [
        "BITACORA_T02.md",
        "PHASE1_SPEC.md",
        "PHASE2_SPEC.md",
        "PHASE3_SPEC.md",
        "PITCH_T02.md",
        "PREWORK.md",
        "README.md",
        "STARTER.md",
    ], f"docs/ must contain only official docs (PREWORK.md, STARTER.md) and T02 docs, found: {doc_md_files}"

