from video_grounding.settings import Settings, config_hash

# Pinned from the code BEFORE feature_cache existed: jobs already on disk keep resuming with the same hash.
DEFAULT_HASH_BEFORE_FEATURE_CACHE = "646fca8d7b54ade0b04585b3959a333284f52f33d320733b213507b0c25765da"


def test_config_hash_ignores_feature_cache():
    off = Settings(feature_cache={"dir": None, "max_gb": 1})
    assert config_hash(off) == config_hash(Settings())
    assert config_hash(Settings()) == DEFAULT_HASH_BEFORE_FEATURE_CACHE
