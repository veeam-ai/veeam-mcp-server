# Copyright © Veeam Software Group GmbH. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root for license information.

# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pydantic-settings>=2.0.0",
#     "pydantic>=2.0.0",
# ]
# ///

import argparse
import contextlib
import difflib
import importlib.util
import inspect
import json
import sys
import types
import uuid
from abc import ABC
from pathlib import Path
from traceback import format_exc
from types import ModuleType
from typing import Any
from unittest.mock import patch

from pydantic import BaseModel
from pydantic_settings import BaseSettings


def _bypass_validation_init(self: BaseSettings, **kwargs: Any) -> None:
    """Patched __init__ that skips validation but preserves field defaults.

    Uses model_construct() which creates an instance without validation
    but with field defaults properly set. See:
    https://docs.pydantic.dev/latest/concepts/models/#creating-models-without-validation
    """
    constructed = type(self).model_construct(**kwargs)
    self.__dict__.update(constructed.__dict__)
    if hasattr(constructed, "__pydantic_private__"):
        object.__setattr__(self, "__pydantic_private__", constructed.__pydantic_private__)
    if hasattr(constructed, "__pydantic_extra__"):
        object.__setattr__(self, "__pydantic_extra__", constructed.__pydantic_extra__)


ENV_EXAMPLE_HEADER = """
# DO NOT EDIT. This file is generated automatically by the 'scripts/update_env_example.py' script.
# Copy this file, rename it to '.env', and define the necessary variables.
# Commented variables are not mandatory and their defaults will be used if not defined.

""".lstrip()


def _generate_env_content(settings_dir_path: Path) -> str:
    """Generate the full env example content."""
    init_file = settings_dir_path / "__init__.py"
    if not init_file.exists():
        raise FileNotFoundError(f"__init__.py not found in {settings_dir_path}")

    lines = [ENV_EXAMPLE_HEADER.rstrip()]

    # Collect all unique settings classes from __init__.py only
    unique_classes: dict[int, type[BaseSettings]] = {}
    try:
        settings_classes = _gather_settings_classes_from_file(init_file)
        for settings_class in settings_classes:
            unique_classes[id(settings_class)] = settings_class
    except Exception as e:
        print(f"{init_file} processing failed with error: {e}")
        raise

    # Sort classes alphabetically by their formatted name and generate env example
    sorted_classes = sorted(unique_classes.values(), key=_format_class_name)
    for settings_class in sorted_classes:
        lines.append(_format_settings_section(settings_class))

    return "\n".join(lines) + "\n"


def _gather_settings_classes_from_file(settings_file: Path) -> list[type[BaseSettings]]:
    """Load a settings file and return all BaseSettings classes it contains."""
    settings_file = settings_file.resolve()
    if not settings_file.exists():
        raise FileNotFoundError(settings_file)

    fake_pkg_name = f"_fakepkg_{uuid.uuid4().hex[:8]}"
    # A fake module is needed to load dependencies via relative paths.
    fake_pkg_mod = types.ModuleType(fake_pkg_name)
    fake_pkg_mod.__path__ = [str(settings_file.parent)]
    sys.modules[fake_pkg_name] = fake_pkg_mod

    settings_mod_name = f"{fake_pkg_name}.{settings_file.stem}"
    spec = importlib.util.spec_from_file_location(settings_mod_name, settings_file)
    if spec is None:
        sys.modules.pop(fake_pkg_name, None)
        raise ValueError(f"Failed to load settings file: {settings_file}")
    module = importlib.util.module_from_spec(spec)
    module.__package__ = fake_pkg_name

    # Patch BaseSettings.__init__ to skip validation while preserving field defaults.
    # Settings modules may resolve files CWD-relative (at runtime the CWD is the project
    # root), so the import runs from there.
    with patch.object(BaseSettings, "__init__", _bypass_validation_init), contextlib.chdir(settings_file.parents[2]):
        if spec.loader is None:
            raise ValueError(f"Failed to load settings file: {settings_file}")
        spec.loader.exec_module(module)

    return _get_settings_classes(module)


def _get_settings_classes(module: ModuleType) -> list[type[BaseSettings]]:
    """Retrieve all instantiated BaseSettings classes in the module (not just imported class definitions)."""
    instantiated_classes = []
    for name, obj in inspect.getmembers(module):
        # Skip classes, functions, and other non-instance objects
        if inspect.isclass(obj) or inspect.isfunction(obj) or inspect.ismethod(obj):
            continue
        # Check if the object is an instance of a BaseSettings subclass
        if isinstance(obj, BaseSettings):
            settings_class = type(obj)
            if settings_class is not BaseSettings and ABC not in settings_class.__bases__:
                instantiated_classes.append(settings_class)
    return instantiated_classes


def _format_class_name(settings_class: type[BaseSettings]) -> str:
    """Extract and format the class name by removing Config and Settings suffixes."""
    return settings_class.__name__.replace("Config", "").replace("Settings", "").strip()


def _format_settings_section(settings_class: type[BaseSettings]) -> str:
    """Format a complete settings section with header and environment variables."""
    class_name = _format_class_name(settings_class)
    header = f"# {'=' * 10} {class_name} {'=' * 10}"
    env_vars = _generate_env_example(settings_class)
    return f"{header}\n{env_vars}\n"


def _generate_env_example(settings_class: type[BaseSettings]) -> str:
    """Generate the .env example lines for a given settings class."""
    env_prefix = settings_class.model_config.get("env_prefix", "")
    required_fields = []
    optional_fields = []

    for field_name, field in settings_class.model_fields.items():
        if field.exclude:
            continue

        env_var = field.alias or f"{env_prefix}{field_name.upper()}"
        field_lines = [f"# {field.description}"] if field.description else []

        if field.is_required():
            field_lines.append(f"{env_var}=")
            required_fields.extend(field_lines)
        else:
            field_lines.append(f"# {env_var}={_stringify_value(field.default)}")
            optional_fields.extend(field_lines)

    return "\n".join(required_fields + optional_fields)


def _stringify_value(value: Any) -> str:
    if isinstance(value, list):
        return "'" + json.dumps([v.model_dump() if isinstance(v, BaseModel) else v for v in value]) + "'"
    if isinstance(value, BaseModel):
        return "'" + value.model_dump_json() + "'"
    return str(value)


def _print_diff(existing: str, generated: str) -> None:
    """Print a unified diff between existing and generated content."""
    existing_lines = existing.splitlines(keepends=True)
    generated_lines = generated.splitlines(keepends=True)

    diff = difflib.unified_diff(
        existing_lines,
        generated_lines,
        fromfile="existing",
        tofile="generated",
        lineterm="",
    )

    for line in diff:
        print(line, end="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate .env.example files from settings.")
    parser.add_argument("--settings-dir", type=Path, required=True, help="Path to the settings directory.")
    parser.add_argument(
        "--env-example-path", type=Path, required=True, help="Path to the .env.example file to generate."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if generation would result in a different file. Exit with error code 1 if different.",
    )

    args = parser.parse_args()

    try:
        generated_content = _generate_env_content(args.settings_dir)

        if args.check:
            if not args.env_example_path.exists():
                print(f"Error: {args.env_example_path} does not exist")
                sys.exit(1)
            existing_content = args.env_example_path.read_text()
            if existing_content != generated_content:
                print(f"Error: {args.env_example_path} is out of date")
                print("\nDifferences:")
                _print_diff(existing_content, generated_content)
                sys.exit(1)
            print(f"OK: {args.env_example_path} is up to date")
        else:
            args.env_example_path.write_text(generated_content)
            print(f"Generated {args.env_example_path}")
    except Exception:
        print(f"Error while generating {args.env_example_path}: {format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
