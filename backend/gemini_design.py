import importlib.util
import json
import os
import re
from env_config import load_kopiiki_env


DEFAULT_GEMINI_MODEL = "gemini-3-pro-preview"
load_kopiiki_env()


class GeminiDesignError(RuntimeError):
    pass


def gemini_model_name():
    return os.environ.get("KOPIIKI_GEMINI_MODEL", DEFAULT_GEMINI_MODEL)


def gemini_mock_enabled():
    return os.environ.get("KOPIIKI_GEMINI_MOCK", "").strip().lower() in {"1", "true", "yes"}


def ensure_gemini_configured():
    if gemini_mock_enabled():
        return None
    if not os.environ.get("GEMINI_API_KEY"):
        return "GEMINI_API_KEY is required for Design Capsule AI mode."
    try:
        genai_spec = importlib.util.find_spec("google.genai")
    except ModuleNotFoundError:
        genai_spec = None
    if genai_spec is None:
        return "google-genai is not installed. Install backend requirements before using Design Capsule AI mode."
    return None


def extract_json_object(text):
    if not text:
        raise GeminiDesignError("Gemini returned an empty response.")
    stripped = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", stripped, flags=re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise GeminiDesignError(f"Gemini returned invalid JSON: {exc.msg}.") from exc


def synthesize_design_capsule(evidence, public_evidence):
    if gemini_mock_enabled():
        return mock_design_response(public_evidence)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        model = gemini_model_name()
        contents = [build_prompt(public_evidence)]

        for image in evidence.get("image_inputs", [])[:12]:
            data = image.get("data")
            if not data:
                continue
            contents.append(types.Part.from_bytes(data=data, mime_type=image.get("mime_type", "image/jpeg")))

        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.25,
            ),
        )
        parsed = extract_json_object(getattr(response, "text", ""))
        return normalize_design_response(parsed, public_evidence, model=model)
    except GeminiDesignError:
        raise
    except Exception as exc:
        raise GeminiDesignError(f"Gemini analysis failed: {classify_gemini_error(exc)}") from exc


def classify_gemini_error(exc):
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if "quota" in lowered or "rate" in lowered or "429" in lowered:
        return f"quota or rate limit error ({message})"
    if "timeout" in lowered or "deadline" in lowered:
        return f"request timed out ({message})"
    if "api_key" in lowered or "permission" in lowered or "unauthorized" in lowered or "403" in lowered or "401" in lowered:
        return f"authentication or permission error ({message})"
    return message


def build_prompt(public_evidence):
    evidence_json = json.dumps(public_evidence, ensure_ascii=False, indent=2)
    return f"""
You are generating a Kopiiki Design Capsule for coding agents.

Use the provided browser screenshots and extracted DOM/CSS evidence to create a Markdown-first design standard.
Preserve transferable design decisions, measured relationships, parameter ranges, tolerances, section rhythm, motion logic, responsive behavior, and asset generation prompts.

Do not produce a pixel-perfect clone recipe.
Do not tell agents to reuse source-site images, videos, logos, brand marks, people, product photos, commercial fonts, screenshots, exact proprietary illustrations, or full original copy.
Do not instruct agents to load or purchase the source site's commercial font files. Identify the source typography, then provide open/system fallback stacks that preserve the same role.
All image/video/SVG/icon content must be represented as asset prompts only. Each asset prompt must include asset_id, role, target_format, background, alpha_required, recommended_size, aspect_ratio, placement, prompt, avoid, and implementation_notes.
Be specific about transparent PNG/WebP requirements when a layered asset needs alpha. Be specific about SVG suitability for simple icons, masks, gradients, and code-native decoration.
For each section, output transferable design parameters and rebuild guidance, not exact coordinates or a copy blueprint.
Coverage requirements:
- sectionAnatomy must cover every desktop evidence section, using evidenceId values like section-0, section-1, etc.
- measuredParameters must include stable numeric ranges from evidence: desktop/tablet/mobile bounds when available, width behavior, vertical rhythm, typography role, and component counts.
- layerMap must describe how background, borders, text, media/code, interactive controls, and decorative layers stack for the section.
- assetPrompts must include at least 5 prompts for a multi-section site, covering code-native decorations, transparent assets, SVG icons/patterns, masks/gradients, and any video/loop role when relevant.
- visualCheckpoints must tell a coding agent what to inspect after implementation without requiring source screenshots.

Return strict JSON with this shape:
{{
  "designThesis": string,
  "tokens": {{
    "colors": [{{"name": string, "value": string, "usage": string, "confidence": number}}],
    "typography": [{{"role": string, "family": string, "sizeRange": string, "weight": string, "lineHeight": string, "notes": string}}],
    "spacing": [{{"name": string, "valueRange": string, "usage": string}}],
    "radii": [{{"name": string, "valueRange": string, "usage": string}}],
    "effects": [{{"name": string, "css": string, "usage": string}}]
  }},
  "fontStrategy": [{{"role": string, "sourceFamily": string, "recommendedStack": string, "licensingNote": string, "implementationNotes": string}}],
  "sectionAnatomy": [{{"id": string, "evidenceId": string, "role": string, "measuredParameters": [string], "stableDimensions": [string], "layerStack": [string], "layerMap": [string], "componentFamilies": [string], "motion": string, "responsive": string, "rebuildGuidance": string, "implementationChecklist": [string], "do": [string], "dont": [string]}}],
  "layoutGrammar": [string],
  "componentFamilies": [{{"name": string, "rules": [string], "states": [string], "tolerances": [string]}}],
  "motion": [{{"name": string, "timing": string, "purpose": string, "reducedMotion": string}}],
  "responsive": [{{"breakpoint": string, "behavior": string, "preserve": [string], "mayChange": [string]}}],
  "assetPrompts": [{{"asset_id": string, "role": string, "target_format": string, "background": string, "alpha_required": boolean, "recommended_size": string, "aspect_ratio": string, "placement": string, "prompt": string, "avoid": [string], "implementation_notes": string}}],
  "visualCheckpoints": [{{"scope": string, "checks": [string], "tolerance": string}}],
  "doDont": {{"do": [string], "dont": [string]}},
  "confidence": number
}}

Evidence:
{evidence_json}
"""


def normalize_design_response(data, public_evidence, model=None):
    data = data if isinstance(data, dict) else {}
    normalized = {
        "schema": "kopiiki.design-capsule.v1",
        "model": model or gemini_model_name(),
        "designThesis": data.get("designThesis") or "A measured design capsule generated from browser evidence.",
        "tokens": data.get("tokens") if isinstance(data.get("tokens"), dict) else {},
        "fontStrategy": normalize_font_strategy(data.get("fontStrategy"), public_evidence),
        "sectionAnatomy": as_list(data.get("sectionAnatomy")),
        "layoutGrammar": as_list(data.get("layoutGrammar")),
        "componentFamilies": as_list(data.get("componentFamilies")),
        "motion": as_list(data.get("motion")),
        "responsive": as_list(data.get("responsive")),
        "assetPrompts": normalize_asset_prompts(data.get("assetPrompts")),
        "visualCheckpoints": normalize_visual_checkpoints(data.get("visualCheckpoints")),
        "doDont": data.get("doDont") if isinstance(data.get("doDont"), dict) else {"do": [], "dont": []},
        "confidence": safe_float(data.get("confidence"), default=0.55),
    }
    normalized["sectionAnatomy"] = align_section_coverage(normalized["sectionAnatomy"], public_evidence)
    normalized["assetPrompts"] = ensure_asset_prompt_coverage(normalized["assetPrompts"], public_evidence)
    if not normalized["visualCheckpoints"]:
        normalized["visualCheckpoints"] = fallback_visual_checkpoints(public_evidence)
    return normalized


def as_list(value):
    return value if isinstance(value, list) else []


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_asset_prompts(prompts):
    normalized = []
    for index, prompt in enumerate(as_list(prompts)):
        if not isinstance(prompt, dict):
            continue
        normalized.append(
            {
                "asset_id": prompt.get("asset_id") or f"asset-{index + 1}",
                "role": prompt.get("role") or "supporting visual asset",
                "target_format": prompt.get("target_format") or "png",
                "background": prompt.get("background") or "transparent",
                "alpha_required": bool(prompt.get("alpha_required")),
                "recommended_size": prompt.get("recommended_size") or "1600x1200",
                "aspect_ratio": prompt.get("aspect_ratio") or "4:3",
                "placement": prompt.get("placement") or "Use where the design calls for this visual role.",
                "prompt": prompt.get("prompt") or "Generate a non-proprietary visual asset that matches the extracted design language.",
                "avoid": as_list(prompt.get("avoid")) or [
                    "source-site imagery",
                    "logos",
                    "trademark shapes",
                    "readable copied text",
                ],
                "implementation_notes": prompt.get("implementation_notes") or "Do not copy original site assets.",
            }
        )
    return normalized


def normalize_font_strategy(value, public_evidence):
    strategies = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        strategies.append(
            {
                "role": item.get("role") or "Typography role",
                "sourceFamily": item.get("sourceFamily") or item.get("family") or "Observed source font",
                "recommendedStack": item.get("recommendedStack") or "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                "licensingNote": item.get("licensingNote") or "Do not copy or bundle source commercial font files unless licensed.",
                "implementationNotes": item.get("implementationNotes") or "Match proportions, contrast, and rhythm with an available fallback stack.",
            }
        )
    if strategies:
        return strategies
    return fallback_font_strategy(public_evidence)


def normalize_visual_checkpoints(value):
    checkpoints = []
    for item in as_list(value):
        if not isinstance(item, dict):
            continue
        checkpoints.append(
            {
                "scope": item.get("scope") or "Page",
                "checks": as_list(item.get("checks")) or ["Compare hierarchy, rhythm, and component density against the capsule."],
                "tolerance": item.get("tolerance") or "Preserve relationships rather than exact source pixels.",
            }
        )
    return checkpoints


def desktop_sections(public_evidence):
    desktop = next((vp for vp in public_evidence.get("viewports", []) if vp.get("viewport", {}).get("id") == "desktop"), None)
    return (desktop or {}).get("sections", [])


def section_dimensions(public_evidence, index):
    lines = []
    for viewport in public_evidence.get("viewports", []):
        meta = viewport.get("viewport", {})
        section = next((item for item in viewport.get("sections", []) if item.get("index") == index), None)
        if not section:
            continue
        rect = section.get("rect") or {}
        rect_percent = section.get("rectPercent") or {}
        lines.append(
            f"{meta.get('id')}: {rect.get('width')}x{rect.get('height')}px, y={rect.get('y')}px, width={rect_percent.get('width')}% of page."
        )
    return lines


def align_section_coverage(sections, public_evidence):
    evidence_sections = desktop_sections(public_evidence)
    if not evidence_sections:
        return sections or []

    aligned = []
    for index, section in enumerate(sections[: len(evidence_sections)]):
        if not isinstance(section, dict):
            continue
        source = evidence_sections[index]
        enriched = dict(section)
        enriched.setdefault("id", f"section-{index}")
        enriched.setdefault("evidenceId", f"section-{index}")
        enriched.setdefault("stableDimensions", section_dimensions(public_evidence, index))
        enriched.setdefault("layerMap", fallback_layer_map(source))
        enriched.setdefault("implementationChecklist", fallback_section_checklist(source))
        measured = as_list(enriched.get("measuredParameters"))
        for item in section_dimensions(public_evidence, index):
            if item not in measured:
                measured.append(item)
        enriched["measuredParameters"] = measured
        aligned.append(enriched)

    for index in range(len(aligned), len(evidence_sections)):
        aligned.append(fallback_section_from_evidence(public_evidence, evidence_sections[index]))

    return aligned


def ensure_asset_prompt_coverage(prompts, public_evidence):
    covered = list(prompts)
    min_count = 5 if len(desktop_sections(public_evidence)) >= 4 else 3
    fallback_prompts = fallback_asset_prompts(public_evidence)
    existing_ids = {item.get("asset_id") for item in covered if isinstance(item, dict)}
    for prompt in fallback_prompts:
        if len(covered) >= min_count:
            break
        if prompt["asset_id"] in existing_ids:
            continue
        covered.append(prompt)
        existing_ids.add(prompt["asset_id"])
    if not covered:
        covered.append(fallback_asset_prompt())
    return covered


def fallback_sections(public_evidence):
    return [fallback_section_from_evidence(public_evidence, section) for section in desktop_sections(public_evidence)]


def fallback_section_from_evidence(public_evidence, section):
    index = section.get("index", 0)
    style = section.get("style") or {}
    rect = section.get("rect") or {}
    counts = section.get("counts") or {}
    return {
        "id": f"section-{index}",
        "evidenceId": f"section-{index}",
        "role": section.get("heading") or section.get("ariaLabel") or section.get("role") or "Page section",
        "measuredParameters": [
            f"Desktop bounds {rect.get('width')}x{rect.get('height')}px at y={rect.get('y')}px.",
            f"Primary typography {style.get('fontFamily', 'unknown')} at {style.get('fontSize', 'unknown')} / {style.get('lineHeight', 'unknown')}.",
            f"Component counts: buttons={counts.get('buttons', 0)}, links={counts.get('links', 0)}, media={counts.get('media', 0)}, forms={counts.get('forms', 0)}.",
        ] + section_dimensions(public_evidence, index),
        "stableDimensions": section_dimensions(public_evidence, index),
        "layerStack": ["page/background surface", "section boundary/grid layer", "content typography layer", "interactive/media layer"],
        "layerMap": fallback_layer_map(section),
        "componentFamilies": section.get("componentHints", []),
        "motion": style.get("transition", "No strong motion detected."),
        "responsive": "Compare desktop/tablet/mobile dimensions in stableDimensions; preserve hierarchy while allowing column changes.",
        "rebuildGuidance": "Recreate the section role, density, layer order, and responsive relationships; do not copy exact source pixels.",
        "implementationChecklist": fallback_section_checklist(section),
        "do": ["Preserve layout role, density, and visual hierarchy."],
        "dont": ["Do not copy source imagery, logo, proprietary illustration, exact text, or exact coordinates."],
    }


def fallback_layer_map(section):
    style = section.get("style") or {}
    counts = section.get("counts") or {}
    return [
        f"Surface: {style.get('background', 'transparent or inherited background')}.",
        f"Boundary: radius {style.get('borderRadius', 'unknown')}, shadow {style.get('boxShadow', 'none')}.",
        f"Typography: {style.get('fontFamily', 'unknown')} / {style.get('fontSize', 'unknown')} / weight {style.get('fontWeight', 'unknown')}.",
        f"Content/media: {counts.get('media', 0)} media nodes, {counts.get('svgs', 0)} SVG nodes, {counts.get('videos', 0)} video nodes.",
        f"Controls: {counts.get('buttons', 0)} buttons and {counts.get('links', 0)} links.",
    ]


def fallback_section_checklist(section):
    rect = section.get("rect") or {}
    return [
        f"Keep section height within roughly {rect.get('height', 'observed')}px desktop proportion unless content changes.",
        "Verify text hierarchy, section spacing, and layer order before tuning colors.",
        "Use generated or code-native replacement assets only.",
    ]


def fallback_font_strategy(public_evidence):
    fonts = (public_evidence.get("summary", {}) or {}).get("fonts", {}) or {}
    strategies = []
    for family in list(fonts.keys())[:6]:
        lowered = family.lower()
        if "mono" in lowered:
            stack = "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace"
            role = "Code/technical"
        elif "serif" in lowered or "display" in lowered or "sagittaire" in lowered:
            stack = "'Cormorant Garamond', 'Fraunces', Georgia, serif"
            role = "Display/heading"
        else:
            stack = "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
            role = "Body/UI"
        strategies.append(
            {
                "role": role,
                "sourceFamily": family,
                "recommendedStack": stack,
                "licensingNote": "Do not copy or bundle source commercial font files unless licensed.",
                "implementationNotes": "Tune size, weight, line-height, and letter rhythm to match the observed role rather than the exact font file.",
            }
        )
    return strategies or [
        {
            "role": "Body/UI",
            "sourceFamily": "Observed source font",
            "recommendedStack": "Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "licensingNote": "Do not copy or bundle source commercial font files unless licensed.",
            "implementationNotes": "Use system/open fonts and tune metrics to match the design role.",
        }
    ]


def fallback_asset_prompts(public_evidence):
    return [
        fallback_asset_prompt(),
        {
            "asset_id": "generated-background-pattern",
            "role": "background texture / SVG pattern",
            "target_format": "svg",
            "background": "transparent",
            "alpha_required": True,
            "recommended_size": "1440x900",
            "aspect_ratio": "16:10",
            "placement": "Use as a low-opacity code-native section or card background layer.",
            "prompt": "Generate a subtle non-branded geometric or technical texture that matches the extracted spacing, line weight, and restrained palette. Keep it abstract and non-proprietary.",
            "avoid": ["logos", "brand marks", "source-site illustrations", "readable text", "high contrast patterns"],
            "implementation_notes": "Prefer SVG or CSS gradients/masks. Keep opacity low and make it tileable or easily crop-safe.",
        },
        {
            "asset_id": "generated-icon-set",
            "role": "SVG icon family",
            "target_format": "svg",
            "background": "none",
            "alpha_required": True,
            "recommended_size": "24x24",
            "aspect_ratio": "1:1",
            "placement": "Use for small controls, metadata, cards, and navigation affordances.",
            "prompt": "Generate a compact line icon family with consistent stroke width, square optical bounds, and neutral technical shapes. It should support the site language without copying source icons.",
            "avoid": ["source-site icons", "logos", "trademark shapes", "filled pictograms", "readable letters"],
            "implementation_notes": "Use currentColor SVGs with 1.5px to 2px stroke; keep icons accessible with labels in code.",
        },
        {
            "asset_id": "generated-mask-gradient",
            "role": "mask / gradient layer",
            "target_format": "svg",
            "background": "gradient",
            "alpha_required": True,
            "recommended_size": "1600x900",
            "aspect_ratio": "16:9",
            "placement": "Use behind hero, code, or feature sections as a subtle depth layer when the design calls for atmosphere.",
            "prompt": "Generate a restrained monochrome or near-neutral gradient mask with soft falloff and precise edges. The effect should support hierarchy without becoming a decorative blob.",
            "avoid": ["colorful blobs", "source-site proprietary artwork", "photos", "logos", "text"],
            "implementation_notes": "Prefer CSS radial/linear gradients or SVG masks; do not bake in source imagery.",
        },
        {
            "asset_id": "generated-card-detail",
            "role": "card detail / transparent PNG",
            "target_format": "png",
            "background": "transparent",
            "alpha_required": True,
            "recommended_size": "1024x1024",
            "aspect_ratio": "1:1",
            "placement": "Use sparingly inside repeated cards or document-like panels when an abstract visual anchor is needed.",
            "prompt": "Generate a clean abstract technical object or document detail with restrained contrast, transparent background, and generous padding. It should match the extracted design language without copying any source-site object, logo, or layout.",
            "avoid": ["logos", "people", "screenshots", "source products", "trademark silhouettes", "readable copied text"],
            "implementation_notes": "Clean alpha edges required. Keep safe padding on all sides and avoid baked shadows unless specified by the component.",
        },
    ]


def fallback_visual_checkpoints(public_evidence):
    checkpoints = []
    for section in desktop_sections(public_evidence)[:10]:
        index = section.get("index", len(checkpoints))
        role = section.get("heading") or section.get("ariaLabel") or section.get("role") or f"section-{index}"
        checkpoints.append(
            {
                "scope": f"section-{index}: {role}",
                "checks": [
                    "Confirm the section role and reading order match the capsule.",
                    "Confirm spacing, typography contrast, and component density match the measured ranges.",
                    "Confirm assets are generated/code-native replacements rather than source media.",
                ],
                "tolerance": "Aim for close visual language and layout rhythm; do not chase pixel-perfect source coordinates.",
            }
        )
    return checkpoints


def fallback_asset_prompt():
    return {
        "asset_id": "generated-supporting-visual",
        "role": "supporting visual asset",
        "target_format": "png",
        "background": "transparent",
        "alpha_required": True,
        "recommended_size": "1600x1200",
        "aspect_ratio": "4:3",
        "placement": "Use as a replaceable visual anchor in the section that needs media.",
        "prompt": "Generate a non-proprietary visual asset that matches the extracted design language, with clean transparent background and generous padding. Do not copy the source site's logo, photography, products, illustrations, or text.",
        "avoid": ["logos", "readable copied text", "trademark shapes", "source-site imagery", "people"],
        "implementation_notes": "Transparent alpha is required. Keep edges clean and do not bake in cast shadows unless the layout specifically asks for them.",
    }


def mock_design_response(public_evidence):
    return normalize_design_response(
        {
            "designThesis": "A mock Design Capsule generated from deterministic evidence for local validation.",
            "tokens": {
                "colors": [
                    {"name": "dominant-background", "value": next(iter(public_evidence.get("summary", {}).get("colors", {}) or {"unknown": 1}), "unknown"), "usage": "Primary page surface", "confidence": 0.5}
                ],
                "typography": [],
                "spacing": [],
                "radii": [],
                "effects": [],
            },
            "layoutGrammar": ["Preserve section roles and measured relationships; do not preserve source pixels."],
            "componentFamilies": [],
            "motion": [],
            "responsive": [],
            "fontStrategy": [],
            "assetPrompts": [],
            "visualCheckpoints": [],
            "doDont": {
                "do": ["Use generated assets and code-native UI."],
                "dont": ["Do not copy source media or brand marks."],
            },
            "confidence": 0.5,
        },
        public_evidence,
        model="mock-gemini",
    )
