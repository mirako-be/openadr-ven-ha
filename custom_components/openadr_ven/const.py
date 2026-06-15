DOMAIN = "openadr_ven"

CONF_VTN_URL       = "vtn_url"
CONF_VEN_NAME      = "ven_name"
CONF_TARGET_ENTITY = "target_entity"

# OpenADR 3.0 OAuth2
CONF_CLIENT_ID     = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_TOKEN_URL     = "token_url"
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 60  # seconds

# SIMPLE level mapping options
CONF_LEVEL_0_PCT = "level_0_pct"
CONF_LEVEL_1_PCT = "level_1_pct"
CONF_LEVEL_2_PCT = "level_2_pct"
CONF_LEVEL_3_PCT = "level_3_pct"

DEFAULTS = {
    CONF_LEVEL_0_PCT: 100,
    CONF_LEVEL_1_PCT: 75,
    CONF_LEVEL_2_PCT: 50,
    CONF_LEVEL_3_PCT: 0,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
}
