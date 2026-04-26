from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ModelScope 魔搭社区推理 API（OpenAI 兼容），优先于 DashScope
    modelscope_api_key: str = ""
    modelscope_base_url: str = "https://api-inference.modelscope.cn/v1"
    modelscope_model: str = "Qwen/Qwen3.5-27B"

    # 阿里云 DashScope（兼容 OpenAI 的 Chat Completions）
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-turbo"
    log_dir: Path = Path("logs")
    # Absolute or relative path to `vite build` output (single-port production).
    frontend_dist: Path | None = None


def get_settings() -> Settings:
    return Settings()


def has_api_key(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(
        (s.modelscope_api_key and s.modelscope_api_key.strip())
        or (s.dashscope_api_key and s.dashscope_api_key.strip())
    )


def uses_modelscope(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.modelscope_api_key and s.modelscope_api_key.strip())
