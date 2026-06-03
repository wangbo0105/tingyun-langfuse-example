from pathlib import Path

from dotenv import load_dotenv
import uvicorn

load_dotenv(Path(__file__).parent / ".env")


def main():
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=False)


if __name__ == "__main__":
    main()
