"""
NETRA Plugin Playground Package
Provides contracts, registry, defaults, presets, and A/B test framework.
"""

from .contracts import VISION_CONTRACT_DOC, TRACKING_CONTRACT_DOC, CONTROL_CONTRACT_DOC
from .registry import registry

__all__ = [
    "VISION_CONTRACT_DOC",
    "TRACKING_CONTRACT_DOC",
    "CONTROL_CONTRACT_DOC",
    "registry",
]
