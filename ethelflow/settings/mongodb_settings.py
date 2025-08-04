from pydantic_settings import BaseSettings, SettingsConfigDict


class MongoDBSettings(BaseSettings):
    """
    Settings for MongoDB connection.
    """

    uri: str
    database_name: str = "ethelflow"

    model_config = SettingsConfigDict(
        env_prefix="ETHELFLOW_MONGODB_",
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = MongoDBSettings()
