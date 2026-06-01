DOMAIN = "openadr_ven"

CONF_VTN_URL        = "vtn_url"
CONF_VEN_NAME       = "ven_name"
CONF_CERT_PATH      = "cert_path"
CONF_KEY_PATH       = "key_path"
CONF_CA_CERT_PATH   = "ca_cert_path"
CONF_VERIFY_TLS     = "verify_tls"
CONF_TARGET_ENTITY  = "target_entity"

# Options (editable post-setup via options flow)
CONF_LEVEL_0_PCT    = "level_0_pct"
CONF_LEVEL_1_PCT    = "level_1_pct"
CONF_LEVEL_2_PCT    = "level_2_pct"
CONF_LEVEL_3_PCT    = "level_3_pct"

DEFAULTS = {
    CONF_LEVEL_0_PCT: 100,
    CONF_LEVEL_1_PCT: 75,
    CONF_LEVEL_2_PCT: 50,
    CONF_LEVEL_3_PCT: 0,
}

SIMPLE_LEVELS = [0, 1, 2, 3]
