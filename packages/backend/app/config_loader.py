"""
Settings loader — loads TOML configuration and prompt templates.

Modeled after PR-Agent's config_loader.py which uses Dynaconf for hierarchical
configuration with environment variable overrides.
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Optional

import tomli

logger = logging.getLogger(__name__)

_SETTINGS_DIR = Path(__file__).parent / "settings"
_CACHE: dict[str, Any] = {}


def _load_toml(filename: str) -> dict[str, Any]:
    """Load and cache a TOML file from the settings directory."""
    if filename in _CACHE:
        return _CACHE[filename]

    filepath = _SETTINGS_DIR / filename
    if not filepath.exists():
        logger.warning("Settings file not found: %s", filepath)
        return {}

    with open(filepath, "rb") as f:
        data = tomli.load(f)

    _CACHE[filename] = data
    return data


def get_settings(section: Optional[str] = None) -> dict[str, Any]:
    """
    Load configuration.toml and return settings.

    Parameters
    ----------
    section : str, optional
        Return only a specific section (e.g. 'pr_reviewer').
        If None, returns the entire configuration dict.
    """
    config = _load_toml("configuration.toml")

    # Allow environment variables to override (ENV vars take precedence)
    # Format: SWEAGENT_<SECTION>__<KEY> e.g. SWEAGENT_CONFIG__MODEL
    env_prefix = "SWEAGENT_"
    for key, val in os.environ.items():
        if key.startswith(env_prefix):
            parts = key[len(env_prefix):].lower().split("__")
            if len(parts) == 2:
                sec, setting = parts
                if sec not in config:
                    config[sec] = {}
                config[sec][setting] = val

    if section:
        return config.get(section, {})
    return config


def get_prompt(prompt_file: str, prompt_key: str) -> dict[str, str]:
    """
    Load a prompt template TOML and return the system/user prompts.

    Parameters
    ----------
    prompt_file : str
        TOML filename (e.g. 'pr_reviewer_prompts.toml')
    prompt_key : str
        Top-level key in the TOML (e.g. 'pr_review_prompt')

    Returns
    -------
    dict with 'system' and 'user' keys
    """
    data = _load_toml(prompt_file)
    prompt_data = data.get(prompt_key, {})

    return {
        "system": prompt_data.get("system", ""),
        "user": prompt_data.get("user", ""),
    }


def reload_settings() -> None:
    """Clear the settings cache to force a reload on next access."""
    _CACHE.clear()
