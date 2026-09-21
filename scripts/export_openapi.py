import json

from backend.app.main import app

if __name__ == "__main__":
    with open("docs/openapi.json", "w", encoding="utf-8") as handle:
        json.dump(app.openapi(), handle, ensure_ascii=False, indent=2)
