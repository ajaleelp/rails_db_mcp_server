"""Configuration loader for the Rails MCP server."""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import translate
import re
from pathlib import Path
from typing import Dict, List, Any

import yaml


@dataclass(frozen=True)
class RateLimitConfig:
    """Simple rate-limit configuration container."""

    requests_per_minute: int = 30


@dataclass(frozen=True)
class MCPConfig:
    """Structured representation of MCP configuration."""

    sensitive_fields: Dict[str, List[str]] = field(default_factory=dict)
    sensitive_patterns: List[str] = field(default_factory=list)
    masking_rules: Dict[str, str] = field(default_factory=dict)
    return_columns: Dict[str, List[str]] = field(default_factory=dict)
    excluded_tables: List[str] = field(default_factory=list)
    default_limit: int = 10
    max_limit: int = 100
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    compiled_sensitive_patterns: List[re.Pattern[str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPConfig":
        rl_data = data.get('rate_limit', {}) or {}
        rate_limit = RateLimitConfig(requests_per_minute=int(rl_data.get('requests_per_minute', 30)))
        compiled_patterns = [
            re.compile(translate(pattern), re.IGNORECASE)
            for pattern in data.get('sensitive_patterns', [])
        ]
        return cls(
            sensitive_fields=data.get('sensitive_fields', {}),
            sensitive_patterns=data.get('sensitive_patterns', []),
            masking_rules=data.get('masking_rules', {}),
            return_columns=data.get('return_columns', {}),
            excluded_tables=data.get('excluded_tables', []),
            default_limit=int(data.get('default_limit', 10)),
            max_limit=int(data.get('max_limit', 100)),
            rate_limit=rate_limit,
            compiled_sensitive_patterns=compiled_patterns,
        )


class ConfigLoader:
    """Load YAML config files and merge with defaults."""

    DEFAULTS: Dict[str, Any] = {
        'sensitive_fields': {},
        'sensitive_patterns': [
            '*password*',
            '*token*',
            '*secret*',
        ],
        'masking_rules': {},
        'return_columns': {},
        'excluded_tables': ['schema_migrations', 'ar_internal_metadata'],
        'default_limit': 10,
        'max_limit': 100,
        'rate_limit': {'requests_per_minute': 30},
    }

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path

    def load(self) -> MCPConfig:
        """Load configuration file if present, falling back to defaults."""
        user_data: Dict[str, Any] = {}
        if self.config_path and self.config_path.exists():
            raw = yaml.safe_load(self.config_path.read_text())
            if isinstance(raw, dict):
                user_data = raw
        merged = self._merge_dicts(self.DEFAULTS, user_data)
        return MCPConfig.from_dict(merged)

    def _merge_dicts(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for key, value in base.items():
            if isinstance(value, dict):
                merged[key] = value.copy()
            elif isinstance(value, list):
                merged[key] = list(value)
            else:
                merged[key] = value
        for key, value in (override or {}).items():
            if key in ('sensitive_fields', 'masking_rules', 'return_columns') and isinstance(value, dict):
                merged.setdefault(key, {})
                merged[key].update(value)
                continue
            if key in ('sensitive_patterns', 'excluded_tables') and isinstance(value, list):
                merged.setdefault(key, [])
                merged[key].extend([item for item in value if item not in merged[key]])
                continue
            merged[key] = value
        return merged
