from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "workspace" / "hero_repo"


FILES = {
    "calculator.py": '''def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a - b
''',

    "test_calculator.py": '''from calculator import add


def main():
    actual = add(7, 5)
    expected = 12

    if actual != expected:
        raise AssertionError(
            f"add(7, 5) expected {expected}, got {actual}"
        )

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
''',

    "README.md": '''# Hero Repo

This is a small demonstration repository.

Expected behavior:

- `add(a, b)` returns the sum of `a` and `b`.
- Running `test_calculator.py` should print `ALL TESTS PASSED`.

The current repository contains one intentional bug.
''',
}


def main() -> None:
    DEMO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for name, content in FILES.items():
        path = DEMO_DIR / name

        path.write_text(
            content,
            encoding="utf-8",
        )

        print(f"created: {path}")

    report = ROOT / "workspace" / "hero_debug_report.md"

    if report.exists():
        report.unlink()
        print(f"removed old report: {report}")


if __name__ == "__main__":
    main()