"""Keep local dotenv credentials out of the unit-test configuration."""

from settings import Settings

Settings.model_config["env_file"] = None
