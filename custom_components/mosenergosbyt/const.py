"""Constants for Mosenergosbyt integration."""

DOMAIN = "mosenergosbyt"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 86400

BASE_URL = "https://my.mosenergosbyt.ru"
AUTH_URL = f"{BASE_URL}/auth"
REQUEST_URL = f"{BASE_URL}/gate_lkcomu"
APP_VERSION = "1.29.0"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
