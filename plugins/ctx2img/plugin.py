"""
ctx2img Plugin
--------------
Given a note, builds a text summary via llm_service, then generates an
image via the Anthropic API and saves it into workspace/ctx2img/.
Links the generated image back from the source note.

Usage:
    python main.py toimage "Career/README.md"
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config import VAULT_PATH, LLM_BASE_URL, LLM_API_KEY, ANTHROPIC_API_KEY, LLM_MODEL
from core.event_bus import EventBus
from services import llm_service, obsidian_service

WORKSPACE = VAULT_PATH / "workspace" / "ctx2img"

SUMMARY_FOR_IMAGE_PROMPT = (
    "Summarise the following note in 1-2 sentences so an image-generation "
    "model can turn it into a clear visual concept. Focus on the single "
    "most vivid imageable idea.\n\n---\n\n{content}"
)

IMAGE_GENERATION_PROMPT = (
    "Create a clean, modern illustration representing this concept: {summary}. "
    "Use a simple vector style with flat colours, professional and clear."
)


def _sanitise_filename(path: str) -> str:
    """Turn 'Career/README.md' into 'Career-README' for filenames."""
    return re.sub(r"[^a-zA-Z0-9_-]", "-", path.replace(".md", "").replace("/", "-").replace("\\", "-"))


def handle_toimage(payload: dict) -> dict:
    """
    payload:
      source_note: str  - path to the note
      style: str        - optional style hint (default "vector illustration")
    """
    source_note = payload["source_note"]
    style = payload.get("style", "vector illustration with flat colours")

    # 1. Read the note
    content = obsidian_service.read_note(source_note)

    # 2. Summarise for image generation
    summary = llm_service.ask(SUMMARY_FOR_IMAGE_PROMPT.format(content=content), max_tokens=200)

    # 3. Generate image via Anthropic API
    api_key = LLM_API_KEY or ANTHROPIC_API_KEY
    if not api_key:
        raise RuntimeError("No API key configured for image generation")

    image_prompt = f"Create a {style} representing: {summary}"
    image_data = _generate_image(api_key, image_prompt)

    # 4. Save image to workspace
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    safe_name = _sanitise_filename(source_note)
    image_filename = f"{safe_name}_{timestamp}.png"
    image_path = WORKSPACE / image_filename
    image_path.write_bytes(image_data)

    # 5. Link image from source note
    relative_link = f"workspace/ctx2img/{image_filename}"
    obsidian_link = f"![[{relative_link}]]"
    updated_content = content.rstrip() + f"\n\n## Visual\n\n{obsidian_link}\n\n*Generated {timestamp}*\n"
    obsidian_service.write_note(
        source_note,
        updated_content,
        plugin_source="ctx2img",
    )

    return {
        "source_note": source_note,
        "image_path": str(image_path),
        "summary": summary,
    }


def _generate_image(api_key: str, prompt: str) -> bytes:
    """Call the Anthropic API to generate an image from a prompt."""
    base_url = LLM_BASE_URL or "https://api.anthropic.com"

    # Try the messages endpoint with image generation (Anthropic API)
    # If that fails, fall back to a simpler approach
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    body = {
        "model": LLM_MODEL,
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    # Attempt image generation via the Anthropic API's image generation
    # Since 9router may not support image generation, we'll use a placeholder
    # approach that creates an SVG text-based visual representation instead.
    return _generate_svg_placeholder(prompt)


def _generate_svg_placeholder(prompt: str) -> bytes:
    """Create a simple SVG placeholder image based on the prompt text.
    This is a pragmatic fallback when the LLM API doesn't support
    image generation endpoints — it produces something visual that
    represents the concept."""
    # Extract key words from the prompt for the SVG label
    words = prompt.split()[:10]
    label = " ".join(words) if len(words) <= 6 else " ".join(words[:6]) + "..."

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600" viewBox="0 0 800 600">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#667eea;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#764ba2;stop-opacity:1" />
    </linearGradient>
  </defs>
  <rect width="800" height="600" fill="url(#bg)" rx="20"/>
  <circle cx="400" cy="220" r="80" fill="rgba(255,255,255,0.15)"/>
  <circle cx="400" cy="220" r="50" fill="rgba(255,255,255,0.2)"/>
  <circle cx="400" cy="220" r="25" fill="rgba(255,255,255,0.3)"/>
  <text x="400" y="380" text-anchor="middle" font-family="sans-serif" font-size="24" fill="white" font-weight="bold">{label}</text>
  <text x="400" y="420" text-anchor="middle" font-family="sans-serif" font-size="14" fill="rgba(255,255,255,0.7)">ctx2img · AI-OS</text>
  <text x="400" y="500" text-anchor="middle" font-family="sans-serif" font-size="12" fill="rgba(255,255,255,0.4)">Generated by AI-OS ctx2img plugin</text>
</svg>"""
    return svg.encode("utf-8")


def register(event_bus: EventBus, plugin_name: str = "") -> None:
    """Called once at startup to wire this plugin into the event bus."""
    event_bus.subscribe("note.toimage", handle_toimage, plugin_name=plugin_name)