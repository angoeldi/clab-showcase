#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path


def main() -> None:
    here = Path(__file__).resolve().parent
    src = (here / ".." / "assets" / "template_project").resolve()
    if not src.exists():
        raise SystemExit(f"Template project not found: {src}")

    dst = Path.cwd()
    copied = 0
    skipped = 0

    for p in src.rglob("*"):
        rel = p.relative_to(src)
        target = dst / rel

        if p.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            skipped += 1
            continue

        shutil.copy2(p, target)
        copied += 1

    print(f"Scaffold complete. Copied {copied} files, skipped {skipped} existing files.")
    print("Next:")
    print("- edit configs/domain.yaml")
    print("- edit configs/tutorial.yaml")
    print("- export OPENAI_API_KEY")
    print("- export CLAB_APP_MODULE=clab_bot.server:app")
    print('- run: uvicorn "$CLAB_APP_MODULE" --reload')


if __name__ == "__main__":
    main()
