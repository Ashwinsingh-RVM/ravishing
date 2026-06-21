"""
Main entry point for the Goa DRS VP CP Mapping application
"""
import uvicorn
from .api.endpoints import app
from .config.settings import Settings

settings = Settings()


def main():
    """Run the FastAPI application"""
    uvicorn.run(
        "src.api.endpoints:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
