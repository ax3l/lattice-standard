#!/usr/bin/env python3
"""Convert PALS expanded files between wire format and normalized form.

The PALS wire format serializes named entries as ordered lists of
single-key mappings (names need not be unique):

    facility:
      - fodo_lattice:
          kind: Lattice
          branches:
            - fodo_channel:
                elements:
                  - drift1:
                      kind: Drift

The LinkML schema (pals-expanded.linkml.yaml) describes the equivalent
NORMALIZED form, in which each entry carries its name in an explicit
required ``name`` field:

    facility:
      - name: fodo_lattice
        kind: Lattice
        branches:
          - name: fodo_channel
            elements:
              - name: drift1
                kind: Drift

Also handled:
  * ``authors`` items are wrapped as ``- author: {...}`` on the wire and
    plain objects in normalized form.
  * ``UnionEle.elements`` is a name-keyed mapping on the wire
    (source/lattice-element-kinds.md, s:unionele) and a list with
    explicit ``name`` fields in normalized form; single-key list items
    are accepted on input as well.

Usage:
    normalize_names.py [--denormalize] INPUT [OUTPUT]

Reads YAML (or JSON, a YAML subset) and writes YAML. With no OUTPUT the
result goes to stdout.
"""

import argparse
import re
import sys

import yaml


class PalsSafeLoader(yaml.SafeLoader):
    """SafeLoader with YAML 1.2 float notation.

    PyYAML implements YAML 1.1, where scientific notation requires a
    signed exponent (``1.0e+6``). PALS files use plain ``1.0e6``
    (e.g. ``frequency: 394.0e6`` in the standard's examples), which
    YAML 1.1 would silently load as a string. This loader resolves the
    full YAML 1.2 float syntax, including ``Inf``/``-Inf`` special
    values used by PALS.
    """


PalsSafeLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(
        r"""^(?:
         [-+]?(?:[0-9][0-9_]*)\.[0-9_]*(?:[eE][-+]?[0-9]+)?
        |[-+]?(?:[0-9][0-9_]*)(?:[eE][-+]?[0-9]+)
        |\.[0-9][0-9_]*(?:[eE][-+]?[0-9]+)?
        |[-+]?\.(?:inf|Inf|INF)
        |\.(?:nan|NaN|NAN)
        |[-+]?(?:Inf|inf)
        )$""",
        re.X,
    ),
    list("-+0123456789.Ii"),
)


def load_pals_yaml(stream):
    """Load PALS YAML with the extended float resolver."""
    return yaml.load(stream, Loader=PalsSafeLoader)


def _hoist_item(item, what):
    """Turn a single-key mapping ``{name: {...}}`` into ``{name: ..., ...}``."""
    if not isinstance(item, dict) or len(item) != 1:
        raise ValueError(
            f"each {what} entry must be a single-key mapping "
            f"(the entry's name), got: {item!r}"
        )
    name, fields = next(iter(item.items()))
    if fields is None:
        fields = {}
    if not isinstance(fields, dict):
        raise ValueError(
            f"value of {what} entry {name!r} must be a mapping of its "
            f"properties, got: {fields!r}"
        )
    return {"name": name, **fields}


def _unhoist_item(item, what):
    """Turn ``{name: ..., ...}`` back into a single-key mapping."""
    if not isinstance(item, dict) or "name" not in item:
        raise ValueError(f"each normalized {what} entry needs a 'name': {item!r}")
    fields = {k: v for k, v in item.items() if k != "name"}
    return {item["name"]: fields}


def _normalize_element(element):
    """Normalize one element (recursing into UnionEle sub-elements)."""
    if "elements" in element:
        subs = element["elements"]
        if isinstance(subs, dict):  # name-keyed mapping (UnionEle wire form)
            subs = [{name: fields} for name, fields in subs.items()]
        element["elements"] = [
            _normalize_element(_hoist_item(s, "contained element")) for s in subs
        ]
    return element


def _denormalize_element(element):
    if "elements" in element:
        element["elements"] = {
            e["name"]: {
                k: v
                for k, v in _denormalize_element(e).items()
                if k != "name"
            }
            for e in element["elements"]
        }
    return element


def normalize(doc):
    """Wire format -> normalized form (in place; returns doc)."""
    pals = doc.get("PALS")
    if not isinstance(pals, dict):
        raise ValueError("no 'PALS' root mapping found")

    if "authors" in pals:
        pals["authors"] = [
            a["author"] if isinstance(a, dict) and set(a) == {"author"} else a
            for a in pals["authors"]
        ]

    facility = []
    for entry in pals.get("facility", []):
        entry = _hoist_item(entry, "facility")
        branches = []
        for branch in entry.get("branches", []):
            branch = _hoist_item(branch, "branch")
            branch["elements"] = [
                _normalize_element(_hoist_item(e, "element"))
                for e in branch.get("elements", [])
            ]
            branches.append(branch)
        if branches or "branches" in entry:
            entry["branches"] = branches
        facility.append(entry)
    pals["facility"] = facility
    return doc


def denormalize(doc):
    """Normalized form -> wire format (in place; returns doc)."""
    pals = doc.get("PALS")
    if not isinstance(pals, dict):
        raise ValueError("no 'PALS' root mapping found")

    if "authors" in pals:
        pals["authors"] = [{"author": a} for a in pals["authors"]]

    facility = []
    for entry in pals.get("facility", []):
        if "branches" in entry:
            entry["branches"] = [
                _unhoist_item(
                    {
                        **b,
                        "elements": [
                            _unhoist_item(_denormalize_element(e), "element")
                            for e in b.get("elements", [])
                        ],
                    },
                    "branch",
                )
                for b in entry["branches"]
            ]
        facility.append(_unhoist_item(entry, "facility"))
    pals["facility"] = facility
    return doc


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("input", help="input file (PALS wire or normalized form)")
    parser.add_argument("output", nargs="?", help="output file (default: stdout)")
    parser.add_argument(
        "--denormalize",
        action="store_true",
        help="convert normalized form back to the PALS wire format",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        doc = load_pals_yaml(f)

    doc = denormalize(doc) if args.denormalize else normalize(doc)

    text = yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)
    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
