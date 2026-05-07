import json
import os
import zipfile
from datetime import datetime, timezone
from urllib.parse import urlparse

from design_evidence import collect_design_evidence, strip_image_bytes
from gemini_design import gemini_model_name, synthesize_design_capsule
from webtwin_assets import ExtractionCancelled


def ensure_not_cancelled(cancel_event):
    if cancel_event and cancel_event.is_set():
        raise ExtractionCancelled("Cancelled by user")


def create_design_capsule_zip(url, output_dir, extract_id, temp_zip_path, cancel_event=None, progress_callback=None):
    def progress(message):
        if progress_callback:
            progress_callback(message)

    ensure_not_cancelled(cancel_event)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(temp_zip_path), exist_ok=True)

    try:
        evidence = collect_design_evidence(
            url,
            extract_id=extract_id,
            cancel_event=cancel_event,
            progress_callback=progress,
        )
    except ExtractionCancelled:
        raise
    except Exception as exc:
        raise RuntimeError(f"Design evidence capture failed: {exc}") from exc
    public_evidence = strip_image_bytes(evidence)

    ensure_not_cancelled(cancel_event)
    progress("Sending design evidence and screenshots to Gemini...")
    design = synthesize_design_capsule(evidence, public_evidence)

    ensure_not_cancelled(cancel_event)
    progress("Writing DESIGN.md and agent-ready references...")
    files = build_capsule_files(url, public_evidence, design)

    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path, content in files.items():
            ensure_not_cancelled(cancel_event)
            zipf.writestr(path, content)

    return temp_zip_path, {
        "model": design.get("model") or gemini_model_name(),
        "confidence": design.get("confidence"),
        "asset_prompt_count": len(design.get("assetPrompts") or []),
    }


def build_capsule_files(url, evidence, design):
    return {
        "DESIGN.md": render_design_md(url, evidence, design),
        "design/references/section-anatomy.md": render_section_anatomy(design),
        "design/references/layout-grammar.md": render_layout_grammar(design),
        "design/references/font-strategy.md": render_font_strategy(design),
        "design/references/component-families.md": render_component_families(design),
        "design/references/motion.md": render_motion(design),
        "design/references/responsive.md": render_responsive(design),
        "design/references/asset-prompts.md": render_asset_prompts(design),
        "design/references/visual-checkpoints.md": render_visual_checkpoints(design),
        "design/evidence/observations.md": render_observations_md(evidence),
        "design/evidence/section-map.md": render_section_map(evidence),
        "design/evidence/observations.json": json.dumps(evidence, ensure_ascii=False, indent=2),
        "design/scripts/validate-design-capsule.mjs": VALIDATE_SCRIPT,
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def q(value):
    return json.dumps("" if value is None else value, ensure_ascii=False)


def render_design_md(url, evidence, design):
    parsed = urlparse(url)
    frontmatter = [
        "---",
        "standard: design-capsule",
        "version: 0.1.0",
        f"source: {q(url)}",
        f"domain: {q(parsed.netloc)}",
        f"generated_at: {q(now_iso())}",
        f"model: {q(design.get('model'))}",
        f"confidence: {design.get('confidence', 0.0)}",
        "legalPolicy: \"Do not reuse source-site copyrighted imagery, video, logos, trademarks, commercial fonts, screenshots, or full original copy unless explicitly licensed.\"",
        "assetPolicy: \"Generate replacement assets from prompts only; Kopiiki does not package source media.\"",
        "references:",
        "  sectionAnatomy: design/references/section-anatomy.md",
        "  layoutGrammar: design/references/layout-grammar.md",
        "  fontStrategy: design/references/font-strategy.md",
        "  componentFamilies: design/references/component-families.md",
        "  motion: design/references/motion.md",
        "  responsive: design/references/responsive.md",
        "  assetPrompts: design/references/asset-prompts.md",
        "  visualCheckpoints: design/references/visual-checkpoints.md",
        "---",
        "",
    ]
    body = [
        "# DESIGN.md",
        "",
        "## Design Thesis",
        safe_text(design.get("designThesis")),
        "",
        "## Agent Instructions",
        "- Preserve design decisions, measurements, relationships, and tolerances.",
        "- Do not preserve proprietary pixels, original imagery, brand marks, videos, commercial fonts, or full original copy.",
        "- Generate replacement assets from the prompts in `design/references/asset-prompts.md`.",
        "- Keep real UI text and controls code-native unless an asset prompt explicitly says text belongs inside generated media.",
        "",
        "## Transfer Boundary",
        "- This capsule describes the source site's design language, not a replication blueprint.",
        "- Section anatomy records role, hierarchy, rhythm, layer relationships, and parameter ranges.",
        "- Do not copy exact coordinates, source media, logos, trademark-like silhouettes, or proprietary compositions.",
        "",
        "## Tokens",
        render_tokens(design.get("tokens", {})),
        "",
        "## Font Strategy",
        "See `design/references/font-strategy.md`. Use licensed, open, or system alternatives; do not bundle source commercial fonts by default.",
        "",
        "## Section Anatomy",
        "See `design/references/section-anatomy.md`.",
        "",
        "## Layout Grammar",
        bullet_list(design.get("layoutGrammar")),
        "",
        "## Component Families",
        "See `design/references/component-families.md`.",
        "",
        "## Motion",
        "See `design/references/motion.md`.",
        "",
        "## Responsive Strategy",
        "See `design/references/responsive.md`.",
        "",
        "## Asset Prompts",
        "See `design/references/asset-prompts.md`. These are instructions for a coding agent or image/video generation tool; they are not downloaded source assets.",
        "",
        "## Visual Checkpoints",
        "See `design/references/visual-checkpoints.md`. These replace source screenshots with inspection guidance for implementation review.",
        "",
        "## Do / Don't",
        "### Do",
        bullet_list((design.get("doDont") or {}).get("do")),
        "",
        "### Don't",
        bullet_list((design.get("doDont") or {}).get("dont")),
        "",
        "## Evidence Summary",
        f"- Source URL: `{url}`",
        f"- Viewports: {', '.join(vp.get('viewport', {}).get('id', 'unknown') for vp in evidence.get('viewports', []))}",
        f"- Temporary screenshots analyzed: {len(evidence.get('image_inputs', []))}",
        "- Screenshots and source media are not included in this ZIP.",
        "",
    ]
    return "\n".join(frontmatter + body)


def render_tokens(tokens):
    if not isinstance(tokens, dict) or not tokens:
        return "No token summary was generated."
    parts = []
    for key in ["colors", "typography", "spacing", "radii", "effects"]:
        values = tokens.get(key) or []
        parts.append(f"### {title(key)}")
        if not values:
            parts.append("- No strong pattern detected.")
        elif isinstance(values, list):
            for item in values:
                if isinstance(item, dict):
                    parts.append("- " + "; ".join(f"{k}: {v}" for k, v in item.items()))
                else:
                    parts.append(f"- {item}")
        parts.append("")
    return "\n".join(parts).strip()


def render_section_anatomy(design):
    lines = ["# Section Anatomy", ""]
    for section in design.get("sectionAnatomy") or []:
        lines.extend(
            [
                f"## {safe_text(section.get('id') or 'section')}",
                "",
                f"**Evidence ID:** {safe_text(section.get('evidenceId'))}",
                "",
                f"**Role:** {safe_text(section.get('role'))}",
                "",
                "### Measured Parameters",
                bullet_list(section.get("measuredParameters")),
                "",
                "### Stable Dimensions",
                bullet_list(section.get("stableDimensions")),
                "",
                "### Layer Stack",
                bullet_list(section.get("layerStack")),
                "",
                "### Layer Map",
                bullet_list(section.get("layerMap")),
                "",
                "### Component Families",
                bullet_list(section.get("componentFamilies")),
                "",
                f"**Motion:** {safe_text(section.get('motion'))}",
                "",
                f"**Responsive:** {safe_text(section.get('responsive'))}",
                "",
                f"**Rebuild Guidance:** {safe_text(section.get('rebuildGuidance'))}",
                "",
                "### Implementation Checklist",
                bullet_list(section.get("implementationChecklist")),
                "",
                "### Do",
                bullet_list(section.get("do")),
                "",
                "### Don't",
                bullet_list(section.get("dont")),
                "",
            ]
        )
    return "\n".join(lines)


def render_layout_grammar(design):
    return "# Layout Grammar\n\n" + bullet_list(design.get("layoutGrammar")) + "\n"


def render_font_strategy(design):
    lines = ["# Font Strategy", "", "Do not copy or bundle source commercial font files unless the implementer has an explicit license.", ""]
    for item in design.get("fontStrategy") or []:
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        lines.extend(
            [
                f"## {safe_text(item.get('role') or 'Typography role')}",
                f"- Source family: {safe_text(item.get('sourceFamily'))}",
                f"- Recommended stack: `{safe_text(item.get('recommendedStack'))}`",
                f"- Licensing: {safe_text(item.get('licensingNote'))}",
                f"- Notes: {safe_text(item.get('implementationNotes'))}",
                "",
            ]
        )
    return "\n".join(lines)


def render_component_families(design):
    lines = ["# Component Families", ""]
    for family in design.get("componentFamilies") or []:
        if not isinstance(family, dict):
            lines.extend([f"- {family}", ""])
            continue
        lines.extend(
            [
                f"## {safe_text(family.get('name') or 'Component family')}",
                "",
                "### Rules",
                bullet_list(family.get("rules")),
                "",
                "### States",
                bullet_list(family.get("states")),
                "",
                "### Tolerances",
                bullet_list(family.get("tolerances")),
                "",
            ]
        )
    return "\n".join(lines)


def render_motion(design):
    lines = ["# Motion", ""]
    for item in design.get("motion") or []:
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        lines.extend(
            [
                f"## {safe_text(item.get('name') or 'Motion rule')}",
                f"- Timing: {safe_text(item.get('timing'))}",
                f"- Purpose: {safe_text(item.get('purpose'))}",
                f"- Reduced motion: {safe_text(item.get('reducedMotion'))}",
                "",
            ]
        )
    return "\n".join(lines)


def render_responsive(design):
    lines = ["# Responsive Strategy", ""]
    for item in design.get("responsive") or []:
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        lines.extend(
            [
                f"## {safe_text(item.get('breakpoint') or 'Breakpoint')}",
                f"**Behavior:** {safe_text(item.get('behavior'))}",
                "",
                "### Preserve",
                bullet_list(item.get("preserve")),
                "",
                "### May Change",
                bullet_list(item.get("mayChange")),
                "",
            ]
        )
    return "\n".join(lines)


def render_asset_prompts(design):
    lines = ["# Asset Prompts", "", "Kopiiki does not package source-site media. Generate replacement assets from these prompts.", ""]
    for asset in design.get("assetPrompts") or []:
        lines.extend(
            [
                f"## Asset Prompt: {safe_text(asset.get('asset_id'))}",
                "",
                f"- Role: {safe_text(asset.get('role'))}",
                f"- Format: {safe_text(asset.get('target_format'))}",
                f"- Size: {safe_text(asset.get('recommended_size'))}",
                f"- Aspect ratio: {safe_text(asset.get('aspect_ratio'))}",
                f"- Background: {safe_text(asset.get('background'))}",
                f"- Alpha: {'required' if asset.get('alpha_required') else 'not required'}",
                f"- Placement: {safe_text(asset.get('placement'))}",
                f"- Prompt: {safe_text(asset.get('prompt'))}",
                f"- Avoid: {', '.join(asset.get('avoid') or [])}",
                f"- Notes: {safe_text(asset.get('implementation_notes'))}",
                "",
            ]
        )
    return "\n".join(lines)


def render_visual_checkpoints(design):
    lines = ["# Visual Checkpoints", "", "Use these checks after implementation. They preserve design language without requiring source screenshots.", ""]
    for item in design.get("visualCheckpoints") or []:
        if not isinstance(item, dict):
            lines.append(f"- {item}")
            continue
        lines.extend(
            [
                f"## {safe_text(item.get('scope') or 'Scope')}",
                "",
                "### Checks",
                bullet_list(item.get("checks")),
                "",
                f"**Tolerance:** {safe_text(item.get('tolerance'))}",
                "",
            ]
        )
    return "\n".join(lines)


def render_observations_md(evidence):
    lines = [
        "# Evidence Observations",
        "",
        "This file summarizes deterministic browser evidence. Image bytes were used only as temporary Gemini input and are not included in the archive.",
        "",
        "## Viewports",
    ]
    for viewport in evidence.get("viewports", []):
        meta = viewport.get("viewport", {})
        page = viewport.get("page", {})
        lines.extend(
            [
                f"- {meta.get('id')}: {meta.get('width')}x{meta.get('height')}, page height {page.get('scrollHeight')}px, sections {len(viewport.get('sections', []))}",
            ]
        )
    lines.extend(["", "## Token Summary", "```json", json.dumps(evidence.get("summary", {}), ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def render_section_map(evidence):
    lines = [
        "# Section Map",
        "",
        "Deterministic section evidence for coding agents. Use this as measurement context, not as a pixel-copy blueprint.",
        "",
    ]
    for viewport in evidence.get("viewports", []):
        meta = viewport.get("viewport", {})
        lines.extend([f"## {safe_text(meta.get('id') or 'viewport')} {meta.get('width')}x{meta.get('height')}", ""])
        for section in viewport.get("sections", []):
            rect = section.get("rect") or {}
            rect_percent = section.get("rectPercent") or {}
            counts = section.get("counts") or {}
            style = section.get("style") or {}
            lines.extend(
                [
                    f"### section-{section.get('index')}",
                    f"- Role hint: {safe_text(section.get('heading') or section.get('ariaLabel') or section.get('role') or section.get('tag'))}",
                    f"- Bounds: {rect.get('width')}x{rect.get('height')}px at x={rect.get('x')} y={rect.get('y')}; width={rect_percent.get('width')}%, height={rect_percent.get('height')}% of page.",
                    f"- Typography: {safe_text(style.get('fontFamily'))}; size={style.get('fontSize')}; weight={style.get('fontWeight')}; line-height={style.get('lineHeight')}.",
                    f"- Surface: background={style.get('background')}; radius={style.get('borderRadius')}; shadow={style.get('boxShadow')}.",
                    f"- Counts: buttons={counts.get('buttons', 0)}, links={counts.get('links', 0)}, media={counts.get('media', 0)}, svg={counts.get('svgs', 0)}, forms={counts.get('forms', 0)}.",
                    f"- Component hints: {', '.join(section.get('componentHints') or []) or 'none'}",
                    "",
                ]
            )
    return "\n".join(lines)


def bullet_list(items):
    if not items:
        return "- Not specified."
    return "\n".join(f"- {safe_text(item)}" for item in items)


def safe_text(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).replace("\n", " ").strip()


def title(value):
    return str(value).replace("_", " ").replace("-", " ").title()


VALIDATE_SCRIPT = """#!/usr/bin/env node
import { existsSync, readFileSync } from 'node:fs';

const required = [
  'DESIGN.md',
  'design/references/section-anatomy.md',
  'design/references/layout-grammar.md',
  'design/references/font-strategy.md',
  'design/references/component-families.md',
  'design/references/motion.md',
  'design/references/responsive.md',
  'design/references/asset-prompts.md',
  'design/references/visual-checkpoints.md',
  'design/evidence/section-map.md',
  'design/evidence/observations.json',
  'design/scripts/validate-design-capsule.mjs'
];

const missing = required.filter((path) => !existsSync(path));
if (missing.length) {
  console.error(`Missing required files: ${missing.join(', ')}`);
  process.exit(1);
}

const prompts = readFileSync('design/references/asset-prompts.md', 'utf8');
for (const word of ['Role:', 'Format:', 'Background:', 'Alpha:', 'Size:', 'Aspect ratio:', 'Placement:', 'Prompt:', 'Avoid:', 'Notes:']) {
  if (!prompts.includes(word)) {
    console.error(`Asset prompts missing ${word}`);
    process.exit(1);
  }
}

const design = readFileSync('DESIGN.md', 'utf8');
for (const heading of ['## Design Thesis', '## Agent Instructions', '## Transfer Boundary', '## Tokens', '## Font Strategy', '## Asset Prompts', '## Visual Checkpoints']) {
  if (!design.includes(heading)) {
    console.error(`DESIGN.md missing ${heading}`);
    process.exit(1);
  }
}

const assetBlocks = prompts.split(/^## Asset Prompt:/m).slice(1);
if (!assetBlocks.length) {
  console.error('No asset prompt blocks found.');
  process.exit(1);
}
if (assetBlocks.length < 5) {
  console.error(`Expected at least 5 asset prompt blocks, found ${assetBlocks.length}.`);
  process.exit(1);
}
assetBlocks.forEach((block, index) => {
  for (const word of ['- Role:', '- Format:', '- Size:', '- Background:', '- Alpha:', '- Placement:', '- Prompt:', '- Avoid:']) {
    if (!block.includes(word)) {
      console.error(`Asset prompt ${index + 1} missing ${word}`);
      process.exit(1);
    }
  }
});

const sectionText = readFileSync('design/references/section-anatomy.md', 'utf8');
for (const word of ['Evidence ID:', 'Stable Dimensions', 'Layer Map', 'Implementation Checklist']) {
  if (!sectionText.includes(word)) {
    console.error(`Section anatomy missing ${word}`);
    process.exit(1);
  }
}

console.log('Design Capsule structure looks valid.');
"""
