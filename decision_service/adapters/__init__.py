"""Compatibility adapters between prepared decisions and executable algorithms."""

from .generic_to_activity_v2 import adapt_generic_to_activity_v2
from .generic_to_option_v1 import adapt_generic_to_option_v1
from .scenarios_to_option_v1 import adapt_scenarios_to_option_v1

__all__ = ["adapt_generic_to_activity_v2", "adapt_generic_to_option_v1", "adapt_scenarios_to_option_v1"]
