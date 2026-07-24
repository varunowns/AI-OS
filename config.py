"""
AI-OS Config
------------
Central place for settings. For now this is just environment variables,
loaded via a .env file if present. As AI-OS grows, this can be replaced
by config/ files per the original plan — but a single config.py is enough
for the vertical slice.
"""

import os
from pathlib import Path

# Load a local .env file if python-dotenv is installed and a .env exists.
# Kept optional so the slice runs even without the dependency.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Path to your Obsidian vault root, e.g. "V:/Obsidian"
VAULT_PATH = Path(os.environ.get("AI_OS_VAULT_PATH", "./vault"))

# Anthropic API key — get one at https://console.anthropic.com/
# Leave blank when using a proxy like 9router.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Optional LLM proxy/base URL (e.g. 9router). When set, the Anthropic SDK
# targets this endpoint instead of the default api.anthropic.com.
LLM_BASE_URL = os.environ.get("AI_OS_LLM_BASE_URL", "")

# API key for the proxy (used in place of ANTHROPIC_API_KEY when LLM_BASE_URL is set)
LLM_API_KEY = os.environ.get("AI_OS_LLM_API_KEY", "")

# Which model to call for plugin LLM tasks
LLM_MODEL = os.environ.get("AI_OS_LLM_MODEL", "claude-sonnet-4-6")
