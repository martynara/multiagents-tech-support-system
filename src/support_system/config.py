import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Configuration
    app_env: str = os.getenv("APP_ENV")
    app_debug: bool = os.getenv("APP_DEBUG")
    
    # OpenAI
    openai_api_key: str
    openai_llm_model: str = os.getenv("OPENAI_LLM_MODEL")
    openai_embedding_model: str = os.getenv("OPENAI_EMBEDDING_MODEL")
    
    # Google Search
    google_cse_id: str = os.getenv("GOOGLE_CSE_ID")
    google_api_key: str = os.getenv("GOOGLE_API_KEY")
    
    # Database 
    db_host: str = os.getenv("DB_HOST")
    db_port: str = os.getenv("DB_PORT")
    db_name: str = os.getenv("DB_NAME")
    db_user: str = os.getenv("DB_USER")
    db_password: str = os.getenv("DB_PASSWORD")
    
    # Elasticsearch
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL")
    elasticsearch_index_name: str = os.getenv("ELASTICSEARCH_INDEX_NAME")
    elasticsearch_api_key: str = os.getenv("ELASTICSEARCH_API_KEY")

    
    # Agent Configuration
    max_iterations: int = 3
    max_docs: int = 5
    max_web_results: int = 2
    
    @property
    def database_url(self) -> str:
        """Build database URL from components."""
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}?sslmode=disable"
    
    @property
    def openai_model(self) -> str:
        """Backward compatibility."""
        return self.openai_llm_model
    
    @property 
    def elasticsearch_index(self) -> str:
        """Backward compatibility."""
        return self.elasticsearch_index_name
    
    class Config:
        env_file = ".env"
        extra = "allow" 

settings = Settings()