#!/usr/bin/env python3
"""Validate a PALS expanded file against the LinkML schema.

This is the one-stop validation entry point for files in the PALS wire
format. It:

  1. normalizes the file (see normalize_names.py) so single-key named
     entries become explicit ``name`` fields,
  2. generates a closed JSON Schema from pals-expanded.linkml.yaml,
  3. opens the MetaP definition only (``additionalProperties: true``) —
     MetaP may hold arbitrary custom metadata per the standard, while
     unknown keys anywhere else remain validation errors,
  4. validates and reports all errors.

Usage:
    validate_pals.py FILE [FILE ...]
    validate_pals.py --normalized FILE   # skip the normalization step

Exit code 0 if all files are valid, 1 otherwise.

Requires: pip install linkml (pulls in jsonschema and pyyaml).
"""

import argparse
import functools
import sys
from pathlib import Path

import jsonschema

from normalize_names import load_pals_yaml, normalize

SCHEMA_PATH = Path(__file__).parent / "pals-expanded.linkml.yaml"
ROOT_CLASS = "PalsFile"
OPEN_CLASSES = ("MetaP",)


@functools.lru_cache(maxsize=1)
def json_schema() -> dict:
    """Generate the JSON Schema from the LinkML schema (cached)."""
    import json

    from linkml.generators.jsonschemagen import JsonSchemaGenerator

    gen = JsonSchemaGenerator(
        str(SCHEMA_PATH), top_class=ROOT_CLASS, not_closed=False
    )
    schema = json.loads(gen.serialize())
    for cls in OPEN_CLASSES:
        schema["$defs"][cls]["additionalProperties"] = True
    # linkml:Any means "anything", but the generator emits a type list
    # that misses "array"; drop the constraint entirely.
    schema["$defs"].get("Any", {}).pop("type", None)
    return schema


def validate_file(path: str, normalized: bool = False) -> list[str]:
    """Validate one file; returns a list of error messages."""
    with open(path) as f:
        doc = load_pals_yaml(f)
    if not normalized:
        doc = normalize(doc)
    validator = jsonschema.Draft7Validator(json_schema())
    errors = []
    for err in validator.iter_errors(doc):
        loc = "/" + "/".join(str(p) for p in err.absolute_path)
        errors.append(f"{loc}: {err.message}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("files", nargs="+", help="PALS expanded file(s) to validate")
    parser.add_argument(
        "--normalized",
        action="store_true",
        help="input is already in normalized form (skip name hoisting)",
    )
    args = parser.parse_args()

    any_invalid = False
    for path in args.files:
        try:
            errors = validate_file(path, normalized=args.normalized)
        except ValueError as exc:  # structural wire-format error
            errors = [str(exc)]
        if errors:
            any_invalid = True
            print(f"INVALID  {path}")
            for e in errors:
                print(f"    {e}")
        else:
            print(f"valid    {path}")
    sys.exit(1 if any_invalid else 0)


if __name__ == "__main__":
    main()
