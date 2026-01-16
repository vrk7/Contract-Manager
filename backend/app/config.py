import os
from pathlib import Path
from functools import lru_cache


class Settings:
    app_name: str = "Contract Clause Analyzer"
    anthropic_api_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-opus-20240229")

    _in_container = os.path.exists("/.dockerenv")
    _default_db = (
        "postgres+asyncpg://analyzer:analyzer@db:5432/analyzer"
        if _in_container
        else "sqlite+aiosqlite:///./data/app.db"
    )
    
    database_url: str = os.getenv("DATABASE_URL", _default_db)
    chroma_dir: str = os.getenv("CHROMA_DIR", "./data/chroma")
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    rate_limit_stream_per_minute: int = int(
        os.getenv("RATE_LIMIT_STREAM_PER_MINUTE", "60")
    )
    playbook_seed_path: str = os.getenv(
        "PLAYBOOK_SEED_PATH", "./standard_terms_playbook.md"
    )
    cost_per_input_token: float = float(os.getenv("COST_PER_INPUT_TOKEN", "0.000015"))
    cost_per_output_token: float = float(
        os.getenv("COST_PER_OUTPUT_TOKEN", "0.000075")
    )  # approx Claude 3.5 Sonnet pricing
    debug_mode: bool = os.getenv("DEBUG_MODE", "false").lower() == "true"
    inline_analysis: bool = os.getenv("INLINE_ANALYSIS", "false").lower() == "true"
    in_memory_mode: bool = os.getenv("BYPASS_DB_FOR_TESTS", "false").lower() == "true"
    chroma_telemetry: bool = os.getenv("CHROMA_TELEMETRY", "false").lower() == "true"

    def resolve_playbook_path(self) -> Path:
        """
        Resolve the configured playbook path, falling back to the repository root
        if the provided path does not exist relative to the current working directory.
        """
        candidate = Path(self.playbook_seed_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        if candidate.exists():
            return candidate

        # Fall back to the repository root (two levels above this file)
        repo_root = Path(__file__).resolve().parents[2]
        fallback = repo_root / Path(self.playbook_seed_path).name
        return fallback

@lru_cache
def get_settings() -> Settings:
    return Settings()
