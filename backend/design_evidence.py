import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

from webtwin_assets import ExtractionCancelled


VIEWPORTS = [
    {"id": "desktop", "width": 1440, "height": 1100, "is_mobile": False},
    {"id": "tablet", "width": 900, "height": 1100, "is_mobile": False},
    {"id": "mobile", "width": 390, "height": 844, "is_mobile": True},
]


def ensure_not_cancelled(cancel_event):
    if cancel_event and cancel_event.is_set():
        raise ExtractionCancelled("Cancelled by user")


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def strip_image_bytes(evidence):
    clean = dict(evidence)
    clean["image_inputs"] = [
        {
            "id": image["id"],
            "viewport": image.get("viewport"),
            "kind": image.get("kind"),
            "section_index": image.get("section_index"),
            "mime_type": image.get("mime_type"),
            "byte_length": len(image.get("data") or b""),
            "note": image.get("note"),
        }
        for image in evidence.get("image_inputs", [])
    ]
    return clean


def summarize_across_viewports(viewports):
    colors = Counter()
    fonts = Counter()
    radii = Counter()
    shadows = Counter()
    transitions = Counter()
    animations = Counter()

    for viewport in viewports:
        tokens = viewport.get("tokens", {})
        colors.update(tokens.get("colors", {}))
        fonts.update(tokens.get("fonts", {}))
        radii.update(tokens.get("radii", {}))
        shadows.update(tokens.get("shadows", {}))
        transitions.update(tokens.get("transitions", {}))
        animations.update(tokens.get("animations", {}))

    return {
        "colors": dict(colors.most_common(24)),
        "fonts": dict(fonts.most_common(12)),
        "radii": dict(radii.most_common(12)),
        "shadows": dict(shadows.most_common(12)),
        "transitions": dict(transitions.most_common(12)),
        "animations": dict(animations.most_common(12)),
    }


def collect_design_evidence(url, extract_id=None, cancel_event=None, progress_callback=None):
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

    start_time = time.time()

    def progress(message):
        if progress_callback:
            progress_callback(message)

    parsed = urlparse(url)
    evidence = {
        "schema": "kopiiki.design-evidence.v1",
        "source_url": url,
        "domain": parsed.netloc,
        "captured_at": now_iso(),
        "viewports": [],
        "summary": {},
        "image_inputs": [],
    }

    progress("Capturing design evidence across desktop, tablet, and mobile viewports...")
    ensure_not_cancelled(cancel_event)

    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )

            for viewport in VIEWPORTS:
                ensure_not_cancelled(cancel_event)
                progress(f"Scanning {viewport['id']} layout and visual system...")

                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": viewport["width"], "height": viewport["height"]},
                    device_scale_factor=1,
                    is_mobile=viewport["is_mobile"],
                    has_touch=viewport["is_mobile"],
                )
                page = context.new_page()

                try:
                    try:
                        page.goto(url, wait_until="networkidle", timeout=30000)
                    except PlaywrightTimeoutError:
                        page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    ensure_not_cancelled(cancel_event)
                    page.wait_for_timeout(900)
                    page.evaluate(
                        """
                        async () => {
                          await new Promise((resolve) => {
                            let total = 0;
                            const distance = 420;
                            const timer = setInterval(() => {
                              window.scrollBy(0, distance);
                              total += distance;
                              if (total >= document.body.scrollHeight - window.innerHeight) {
                                clearInterval(timer);
                                window.scrollTo(0, 0);
                                resolve();
                              }
                            }, 80);
                          });
                        }
                        """
                    )
                    page.wait_for_timeout(500)
                    ensure_not_cancelled(cancel_event)

                    viewport_evidence = page.evaluate(EXTRACT_PAGE_EVIDENCE_JS)
                    viewport_evidence["viewport"] = {
                        "id": viewport["id"],
                        "width": viewport["width"],
                        "height": viewport["height"],
                    }
                    evidence["viewports"].append(viewport_evidence)

                    full_image = page.screenshot(type="jpeg", quality=58, full_page=True)
                    evidence["image_inputs"].append(
                        {
                            "id": f"{viewport['id']}-full-page",
                            "viewport": viewport["id"],
                            "kind": "full_page",
                            "mime_type": "image/jpeg",
                            "data": full_image,
                            "note": "Temporary Gemini analysis input. Not written to output ZIP.",
                        }
                    )

                    if viewport["id"] == "desktop":
                        for section in viewport_evidence.get("sections", [])[:10]:
                            ensure_not_cancelled(cancel_event)
                            rect = section.get("rect") or {}
                            if rect.get("width", 0) < 160 or rect.get("height", 0) < 120:
                                continue
                            try:
                                clip = {
                                    "x": max(0, float(rect.get("x", 0))),
                                    "y": max(0, float(rect.get("y", 0))),
                                    "width": max(160, min(float(rect.get("width", 0)), 1440)),
                                    "height": max(120, min(float(rect.get("height", 0)), 1200)),
                                }
                                crop = page.screenshot(type="jpeg", quality=62, clip=clip)
                                evidence["image_inputs"].append(
                                    {
                                        "id": f"desktop-section-{section.get('index', 0)}",
                                        "viewport": "desktop",
                                        "kind": "section_crop",
                                        "section_index": section.get("index"),
                                        "mime_type": "image/jpeg",
                                        "data": crop,
                                        "note": "Temporary Gemini section crop. Not written to output ZIP.",
                                    }
                                )
                            except Exception:
                                continue
                finally:
                    context.close()

        finally:
            if browser:
                browser.close()

    evidence["summary"] = summarize_across_viewports(evidence["viewports"])
    evidence["capture_duration_seconds"] = round(time.time() - start_time, 3)
    return evidence


EXTRACT_PAGE_EVIDENCE_JS = """
() => {
  const clamp = (value, max = 220) => {
    if (!value) return "";
    const text = String(value).replace(/\\s+/g, " ").trim();
    return text.length > max ? `${text.slice(0, max)}...` : text;
  };
  const isVisible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  };
  const countBy = (values, limit = 20) => {
    const counts = {};
    values.filter(Boolean).forEach((value) => {
      if (value === "rgba(0, 0, 0, 0)" || value === "transparent" || value === "none" || value === "0s") return;
      counts[value] = (counts[value] || 0) + 1;
    });
    return Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, limit));
  };
  const styleSummary = (el) => {
    const style = getComputedStyle(el);
    return {
      display: style.display,
      position: style.position,
      background: style.backgroundColor,
      color: style.color,
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontWeight: style.fontWeight,
      lineHeight: style.lineHeight,
      letterSpacing: style.letterSpacing,
      borderRadius: style.borderRadius,
      boxShadow: style.boxShadow,
      filter: style.filter,
      backdropFilter: style.backdropFilter,
      transition: style.transition,
      animation: style.animationName !== "none" ? `${style.animationName} ${style.animationDuration}` : "none",
    };
  };
  const rootStyle = getComputedStyle(document.documentElement);
  const cssVariables = {};
  for (const name of rootStyle) {
    if (name.startsWith("--")) cssVariables[name] = rootStyle.getPropertyValue(name).trim();
  }

  const sampleElements = Array.from(document.querySelectorAll("body *"))
    .filter(isVisible)
    .slice(0, 420);
  const sampledStyles = sampleElements.map((el) => getComputedStyle(el));

  const tokens = {
    cssVariables,
    colors: countBy(sampledStyles.flatMap((style) => [style.color, style.backgroundColor, style.borderColor]), 28),
    fonts: countBy(sampledStyles.map((style) => style.fontFamily), 12),
    fontSizes: countBy(sampledStyles.map((style) => style.fontSize), 18),
    fontWeights: countBy(sampledStyles.map((style) => style.fontWeight), 12),
    lineHeights: countBy(sampledStyles.map((style) => style.lineHeight), 12),
    radii: countBy(sampledStyles.map((style) => style.borderRadius), 14),
    shadows: countBy(sampledStyles.map((style) => style.boxShadow), 12),
    filters: countBy(sampledStyles.flatMap((style) => [style.filter, style.backdropFilter]), 12),
    transitions: countBy(sampledStyles.map((style) => style.transitionDuration), 10),
    animations: countBy(sampledStyles.map((style) => style.animationDuration), 10),
  };

  let candidates = Array.from(document.querySelectorAll(
    "header, main > section, main > article, section, article, footer, [role='banner'], [role='main'], [role='region'], [role='contentinfo']"
  )).filter(isVisible);
  if (candidates.length < 3) {
    candidates = candidates.concat(Array.from(document.body.children).filter(isVisible));
  }
  const seen = new Set();
  const unique = [];
  for (const el of candidates) {
    if (seen.has(el)) continue;
    seen.add(el);
    const rect = el.getBoundingClientRect();
    if (rect.height < 96 || rect.width < 240) continue;
    unique.push(el);
    if (unique.length >= 10) break;
  }

  const sections = unique.map((el, index) => {
    el.setAttribute("data-kopiiki-section-index", String(index));
    const rect = el.getBoundingClientRect();
    const heading = el.querySelector("h1, h2, h3, [role='heading']");
    const buttons = el.querySelectorAll("button, a[role='button'], input[type='submit'], .btn, [class*='button']");
    const links = el.querySelectorAll("a[href]");
    const media = el.querySelectorAll("img, picture, video, canvas, svg, iframe");
    const images = el.querySelectorAll("img, picture");
    const videos = el.querySelectorAll("video");
    const svgs = el.querySelectorAll("svg");
    const forms = el.querySelectorAll("form, input, textarea, select");
    const directChildren = Array.from(el.children).filter(isVisible).slice(0, 12).map((child, childIndex) => {
      const childRect = child.getBoundingClientRect();
      const childStyle = getComputedStyle(child);
      return {
        index: childIndex,
        tag: child.tagName.toLowerCase(),
        className: clamp(child.className || "", 90),
        textExcerpt: clamp(child.innerText, 100),
        rect: {
          x: Math.round(childRect.left + window.scrollX),
          y: Math.round(childRect.top + window.scrollY),
          width: Math.round(childRect.width),
          height: Math.round(childRect.height),
        },
        style: {
          display: childStyle.display,
          position: childStyle.position,
          zIndex: childStyle.zIndex,
          background: childStyle.backgroundColor,
          fontFamily: childStyle.fontFamily,
          fontSize: childStyle.fontSize,
          fontWeight: childStyle.fontWeight,
          borderRadius: childStyle.borderRadius,
          boxShadow: childStyle.boxShadow,
        }
      };
    });
    return {
      index,
      tag: el.tagName.toLowerCase(),
      id: el.id || "",
      className: clamp(el.className || "", 140),
      role: el.getAttribute("role") || "",
      ariaLabel: el.getAttribute("aria-label") || "",
      heading: heading ? clamp(heading.textContent, 120) : "",
      textExcerpt: clamp(el.innerText, 320),
      rect: {
        x: Math.round(rect.left + window.scrollX),
        y: Math.round(rect.top + window.scrollY),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      rectPercent: {
        x: Math.round(((rect.left + window.scrollX) / Math.max(1, document.documentElement.scrollWidth)) * 1000) / 10,
        y: Math.round(((rect.top + window.scrollY) / Math.max(1, document.documentElement.scrollHeight)) * 1000) / 10,
        width: Math.round((rect.width / Math.max(1, document.documentElement.scrollWidth)) * 1000) / 10,
        height: Math.round((rect.height / Math.max(1, document.documentElement.scrollHeight)) * 1000) / 10,
      },
      style: styleSummary(el),
      counts: {
        buttons: buttons.length,
        links: links.length,
        media: media.length,
        images: images.length,
        videos: videos.length,
        svgs: svgs.length,
        forms: forms.length,
      },
      directChildren,
      componentHints: Array.from(new Set(
        Array.from(el.querySelectorAll("[class], [role]")).slice(0, 80).flatMap((node) => {
          const className = typeof node.className === "string" ? node.className : "";
          const role = node.getAttribute("role") || "";
          return `${className} ${role}`.toLowerCase().split(/\\s+/).filter((part) =>
            /nav|hero|card|button|btn|cta|modal|tab|accordion|carousel|grid|list|menu|form|input|pricing|feature|logo|gallery|media/.test(part)
          );
        })
      )).slice(0, 20),
    };
  });

  return {
    title: document.title || "",
    language: document.documentElement.lang || "",
    url: location.href,
    page: {
      width: window.innerWidth,
      height: window.innerHeight,
      scrollWidth: document.documentElement.scrollWidth,
      scrollHeight: document.documentElement.scrollHeight,
    },
    metadata: {
      description: document.querySelector("meta[name='description']")?.content || "",
      themeColor: document.querySelector("meta[name='theme-color']")?.content || "",
    },
    tokens,
    sections,
  };
}
"""
