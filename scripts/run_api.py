from app.config import settings


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
    )


if __name__ == "__main__":
    main()
