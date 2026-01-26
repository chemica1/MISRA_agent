"""Configuration management for MISRA C Refactoring Agent."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""
    
    # Ollama Configuration
    ollama_model: str = "qwen3-coder:30b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: int = 120

    
    # Agent Configuration
    max_retries: int = 3
    project_root: str = "./target_project"
    violations_csv: str = "./violations.csv"
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "refactoring_log.json"
    state_file: str = "state.json"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
    
    def get_project_root_path(self) -> Path:
        """Get validated project root path."""
        return Path(self.project_root).resolve()
    
    def get_violations_csv_path(self) -> Path:
        """Get validated violations CSV path."""
        return Path(self.violations_csv).resolve()


# Global settings instance
settings = Settings()
