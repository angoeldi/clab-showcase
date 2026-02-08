#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.pyd", ".DS_Store")


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    if not s:
        raise SystemExit("app name must include at least one alphanumeric character")
    return s


def _package_from_slug(slug: str) -> str:
    pkg = slug.replace("-", "_")
    if not pkg.endswith("_example"):
        pkg = f"{pkg}_example"
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", pkg):
        raise SystemExit(f"derived package name is invalid: {pkg}")
    return pkg


def _copy_tree(src: Path, dst: Path, force: bool) -> None:
    if dst.exists():
        if not force:
            raise SystemExit(f"destination already exists: {dst} (use --force to overwrite)")
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)


def _replace_text(path: Path, old: str, new: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Clone an existing conversational labour app package/config into a new app package "
            "so you can adapt domain/tutorial content quickly."
        )
    )
    parser.add_argument("app", help="new app id (e.g. writing-coach)")
    parser.add_argument(
        "--source-package",
        default="haiku_example",
        help="source package directory to copy (default: haiku_example)",
    )
    parser.add_argument(
        "--source-config-dir",
        default="configs/examples/haiku_tutor",
        help="source config directory to copy (default: configs/examples/haiku_tutor)",
    )
    parser.add_argument(
        "--config-id",
        default="",
        help="target config folder name under configs/examples/ (default: slug from app)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite destination package/config directories if they already exist",
    )
    args = parser.parse_args()

    root = Path.cwd()
    src_pkg = (root / args.source_package).resolve()
    src_cfg = (root / args.source_config_dir).resolve()
    if not src_pkg.is_dir():
        raise SystemExit(f"source package not found: {src_pkg}")
    if not src_cfg.is_dir():
        raise SystemExit(f"source config dir not found: {src_cfg}")

    app_slug = _slug(args.app)
    config_id = _slug(args.config_id) if args.config_id else app_slug
    package_name = _package_from_slug(app_slug)

    dst_pkg = root / package_name
    dst_cfg = root / "configs" / "examples" / config_id
    if src_pkg.resolve() == dst_pkg.resolve():
        raise SystemExit("destination package matches source package; choose a different app name")
    if src_cfg.resolve() == dst_cfg.resolve():
        raise SystemExit("destination config directory matches source config directory")

    _copy_tree(src_pkg, dst_pkg, args.force)
    _copy_tree(src_cfg, dst_cfg, args.force)

    old_domain = f"{args.source_config_dir.strip('/')}/domain.yaml"
    old_tutorial = f"{args.source_config_dir.strip('/')}/tutorial.yaml"
    old_users = f"{args.source_config_dir.strip('/')}/users.yaml"
    new_domain = f"configs/examples/{config_id}/domain.yaml"
    new_tutorial = f"configs/examples/{config_id}/tutorial.yaml"
    new_users = f"configs/examples/{config_id}/users.yaml"

    _replace_text(dst_pkg / "server.py", old_domain, new_domain)
    _replace_text(dst_pkg / "server.py", old_tutorial, new_tutorial)
    _replace_text(dst_pkg / "server.py", old_users, new_users)
    _replace_text(dst_pkg / "graph.py", old_domain, new_domain)
    _replace_text(dst_pkg / "graph.py", old_tutorial, new_tutorial)
    _replace_text(dst_pkg / "graph.py", old_users, new_users)

    module = f"{package_name}.server:app"
    print("Created new app scaffold:")
    print(f"- package: {package_name}")
    print(f"- config dir: configs/examples/{config_id}")
    print("")
    print("Run with this app:")
    print(f"export CLAB_APP_MODULE={module}")
    print(f"export CLAB_DOMAIN_PATH={new_domain}")
    print(f"export CLAB_TUTORIAL_PATH={new_tutorial}")
    print(f"export CLAB_USERS_PATH={new_users}")
    print("uvicorn \"$CLAB_APP_MODULE\" --reload")
    print("")
    print("Docker:")
    print("docker compose up --build")


if __name__ == "__main__":
    main()
