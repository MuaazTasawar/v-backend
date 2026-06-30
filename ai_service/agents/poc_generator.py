"""
Generates a complete, professional static PoC website (HTML/CSS/JS) from
a startup's pitch context using the LLM, then deploys it to S3 (Module 3, FE-4).
"""
import json
import logging

from ai_service.dependencies import get_llm
from ai_service.utils.poc_deploy import deploy_poc_site

logger = logging.getLogger(__name__)

POC_SYSTEM_PROMPT = """You are an expert frontend developer building a polished, \
professional landing page / proof-of-concept website for a startup, based on the \
pitch information below. The site should look like a real, modern SaaS or product \
landing page — NOT a generic template. Use a clean, modern design with good \
typography, a clear hero section, a problem/solution section, and a call-to-action.

Startup Name: {startup_name}
Pitch Context: {pitch_context}

Return ONLY a JSON object with exactly these three keys:
{{
  "html": "<complete HTML document, including <head> with inline <style> reference to styles.css and <script> reference to script.js>",
  "css": "<complete CSS content for styles.css — modern, polished, responsive>",
  "js": "<minimal vanilla JS for script.js — simple interactions like smooth scroll or a mobile nav toggle; can be empty string if not needed>"
}}

The HTML must reference styles.css and script.js via relative paths (href="styles.css", src="script.js"). \
Do not include any explanation outside the JSON object. Do not wrap in markdown fences."""


async def generate_and_deploy_poc(startup_id: str, startup_name: str, pitch_context: dict) -> dict:
    """
    Returns: {"live_url": str, "s3_bucket_path": str, "generated_html": str}
    """
    llm = get_llm()
    prompt = POC_SYSTEM_PROMPT.format(
        startup_name=startup_name,
        pitch_context=json.dumps(pitch_context, indent=2),
    )

    response = await llm.ainvoke(prompt)
    raw = response.content.strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("PoC generation returned invalid JSON for startup %s; using fallback template.", startup_id)
        parsed = _fallback_poc(startup_name, pitch_context)

    html = parsed.get("html", "")
    css = parsed.get("css", "")
    js = parsed.get("js", "")

    deployment = deploy_poc_site(startup_id=startup_id, html=html, css=css, js=js)

    return {
        "live_url": deployment["live_url"],
        "s3_bucket_path": deployment["s3_bucket_path"],
        "generated_html": html,
    }


def _fallback_poc(startup_name: str, pitch_context: dict) -> dict:
    """Minimal safe fallback if the LLM response can't be parsed."""
    problem = pitch_context.get("problem", "")
    solution = pitch_context.get("solution", "")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{startup_name}</title>
<link rel="stylesheet" href="styles.css">
</head>
<body>
<header><h1>{startup_name}</h1></header>
<main>
<section><h2>The Problem</h2><p>{problem}</p></section>
<section><h2>Our Solution</h2><p>{solution}</p></section>
</main>
<script src="script.js"></script>
</body>
</html>"""
    css = "body{font-family:sans-serif;margin:0;padding:2rem;max-width:800px;margin:0 auto;}h1{color:#2563eb;}"
    return {"html": html, "css": css, "js": ""}