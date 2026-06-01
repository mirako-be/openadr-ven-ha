DOMAIN = "openadr_ven"

# Protocol versions
CONF_PROTOCOL_VERSION = "protocol_version"
PROTOCOL_V2 = "2.0b"
PROTOCOL_V3 = "3.0"
PROTOCOLS = [PROTOCOL_V2, PROTOCOL_V3]

# Shared connection config
CONF_VTN_URL   = "vtn_url"
CONF_VEN_NAME  = "ven_name"
CONF_TARGET_ENTITY = "target_entity"

# OpenADR 2.0b specific
CONF_CERT_PATH    = "cert_path"
CONF_KEY_PATH     = "key_path"
CONF_CA_CERT_PATH = "ca_cert_path"
CONF_VERIFY_TLS   = "verify_tls"

# OpenADR 3.0 specific
CONF_CLIENT_ID     = "client_id"
CONF_CLIENT_SECRET = "client_secret"
CONF_TOKEN_URL     = "token_url"
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 60  # seconds

# Options (editable post-setup via options flow)
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

SIMPLE_LEVELS = [0, 1, 2, 3]
