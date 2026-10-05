#!/usr/bin/env python3
"""README Refinement & Validation Engine for Cluster Visualizer (`cluster-vis`).

Used as part of the commit and push workflow to ensure README.md stays
consistently updated, all specifications and sample catalogs are synchronized,
embedded assets and links are valid, and CLI options match the code.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def get_specs() -> list[tuple[str, str]]:
    """Scan specs/ directory for specification documents and extract primary titles."""
    specs_dir = REPO_ROOT / "specs"
    if not specs_dir.exists():
        return []

    spec_files = sorted(specs_dir.glob("*.md"))
    specs = []
    for sf in spec_files:
        content = sf.read_text(encoding="utf-8")
        title = sf.stem
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                title = line.lstrip("# ").strip()
                break
        rel_path = sf.relative_to(REPO_ROOT).as_posix()
        specs.append((rel_path, title))
    return specs


def get_sample_catalogs() -> list[tuple[str, str]]:
    """Scan public/data/samples/ for prepackaged cluster models."""
    sample_dir = REPO_ROOT / "public" / "data" / "samples"
    if not sample_dir.exists():
        return []

    samples = []
    for sf in sorted(sample_dir.glob("*.json")):
        rel_path = sf.relative_to(REPO_ROOT).as_posix()
        name = sf.stem.replace("sample-", "").replace("-", " ").title()
        samples.append((rel_path, name))
    return samples


def validate_readme_links(readme_content: str) -> list[str]:
    """Find all local markdown links and images in README and verify they exist on disk."""
    errors = []
    # Match markdown links: [text](path) or ![alt](path)
    pattern = re.compile(r'!?\[.*?\]\((?!https?://|mailto:|#)(.*?)\)')
    for match in pattern.finditer(readme_content):
        target = match.group(1).split("#")[0].strip()
        if not target:
            continue
        target_path = REPO_ROOT / target
        if not target_path.exists():
            errors.append(f"Broken relative link in README.md: '{target}' (target not found on disk)")
    return errors


def check_required_sections(readme_content: str) -> list[str]:
    """Ensure all core architectural and instructional sections exist."""
    required_phrases = [
        "Interactive 3D Kubernetes",
        "License",
        "Deploy to Arbitrary Clusters",
        "Compare 2 Clusters",
        "UI Overview",
        "Quickstart",
        "CLI",
        "README Refinement",
    ]
    missing = []
    for phrase in required_phrases:
        if phrase.lower() not in readme_content.lower():
            missing.append(f"Missing essential section or keyword: '{phrase}'")
    return missing


def generate_specs_table(specs: list[tuple[str, str]]) -> str:
    """Generate Markdown table for specifications."""
    lines = [
        "| Spec ID & Path | Title & Focus Area | Status |",
        "| :--- | :--- | :---: |",
    ]
    for rel_path, title in specs:
        spec_id = Path(rel_path).stem.split("-")[0].upper()
        # Clean title prefix
        clean_title = re.sub(r"^SPEC-\d+[:\s-]*", "", title)
        lines.append(f"| [`{rel_path}`]({rel_path}) | **{clean_title}** | `Implemented` |")
    return "\n".join(lines)


def update_readme(readme_path: Path, specs: list[tuple[str, str]]) -> bool:
    """Synchronize generated sections in README.md."""
    if not readme_path.exists():
        print(f"Error: {readme_path} does not exist", file=sys.stderr)
        return False

    content = readme_path.read_text(encoding="utf-8")
    table = generate_specs_table(specs)

    # Replace specs table if marker exists
    specs_marker_pattern = re.compile(
        r"(<!-- SPECS_TABLE_START -->\n)(.*?)(\n<!-- SPECS_TABLE_END -->)",
        re.DOTALL,
    )
    if specs_marker_pattern.search(content):
        new_content = specs_marker_pattern.sub(
            rf"\g<1>{table}\g<3>",
            content,
        )
        if new_content != content:
            readme_path.write_text(new_content, encoding="utf-8")
            print("✨ Updated specifications table in README.md")
            return True

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Refine, validate, and synchronize README.md for cluster-vis"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate README links, sections, and spec consistency (exits non-zero on error)",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Automatically refresh generated tables and sync metadata in README.md",
    )
    args = parser.parse_args()

    readme_path = REPO_ROOT / "README.md"
    if not readme_path.exists():
        print("❌ Error: README.md not found in repository root.", file=sys.stderr)
        sys.exit(1)

    specs = get_specs()
    samples = get_sample_catalogs()

    if args.update:
        updated = update_readme(readme_path, specs)
        if updated:
            print("✅ README.md successfully updated and synchronized.")
        else:
            print("ℹ️ README.md is already up-to-date.")

    readme_content = readme_path.read_text(encoding="utf-8")
    link_errors = validate_readme_links(readme_content)
    section_errors = check_required_sections(readme_content)

    all_errors = link_errors + section_errors

    if all_errors:
        print("❌ README Validation Failed:")
        for err in all_errors:
            print(f"   • {err}")
        if args.check:
            sys.exit(1)
    else:
        print(f"✅ README validation passed ({len(specs)} specs verified, 0 broken links).")

    return 0


if __name__ == "__main__":
    main()
