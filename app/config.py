from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    root_paths: str = "/data/apps,/opt/stacks"
    scan_depth: int = 1

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def normalized_roots(self) -> list[str]:
        return [part.strip() for part in self.root_paths.split(",") if part.strip()]


settings = Settings()
