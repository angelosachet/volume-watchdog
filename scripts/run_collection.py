from app.collector import run_collection
from app.database import init_db


def main() -> None:
    init_db()
    run_id, scanned_at, scanned_items = run_collection()
    print(f"run_id={run_id}")
    print(f"scanned_at={scanned_at.isoformat()}")
    print(f"scanned_items={scanned_items}")


if __name__ == "__main__":
    main()
