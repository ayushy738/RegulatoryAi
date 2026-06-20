from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    failures: list[tuple[Path, SyntaxError]] = []
    for path in root.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        try:
            compile(source, str(path), "exec")
        except SyntaxError as exc:
            failures.append((path, exc))

    if failures:
        for path, exc in failures:
            print(f"{path}: {exc.msg} at line {exc.lineno}")
        raise SystemExit(1)

    print("Python compile check passed.")


if __name__ == "__main__":
    main()
