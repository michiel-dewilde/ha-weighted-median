"""Constants for the Weighted Median integration."""
DOMAIN = "weighted_median"

CONF_SOURCE_ENTITY = "source_entity"
CONF_WINDOW_SECONDS = "window_seconds"

DEFAULT_WINDOW_SECONDS = 3600  # 1 hour
MIN_WINDOW_SECONDS = 60
MAX_WINDOW_SECONDS = 7 * 24 * 3600  # 1 week
