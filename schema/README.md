# PALS Expanded-Lattice Schema (LinkML)

This directory contains a formal [LinkML](https://linkml.io) schema for the
**expanded** representation of the Particle Accelerator Lattice Standard
(PALS), plus the small tools needed to validate real PALS files against it.

| File | Purpose |
|---|---|
| `pals-expanded.linkml.yaml` | The schema — single source of truth |
| `validate_pals.py` | One-stop validator for PALS wire-format files |
| `normalize_names.py` | Wire format ↔ normalized form converter (used by the validator, also a standalone CLI) |
| `patch_gen_pydantic.py` | Post-processor making `gen-pydantic` output usable |
| `.linkmllint.yaml` | Lint config (disables `standard_naming`: PALS names are normative) |

## What "expanded" means

PALS mandates two representations (`source/overview.md`): the **exact**
representation (a direct translation of the input file) and the **expanded**
representation, in which all beam lines are expanded into branches, all
expressions are evaluated, all `set` commands are applied,
`repeat`/`direction`/subline/superposition constructs are materialized,
`Placeholder` elements are removed, `Fork` elements are processed into
branches, and dependent parameters (`ReferenceP`, `FloorP`, ...) are
computed.

This schema describes **only** the expanded representation: `facility`
contains one or more fully concrete `Lattice` entries — no references,
constants, variables, or expressions. See
`examples/fodo.expanded.pals.yaml` for the expanded form of
`examples/fodo.pals.yaml`.

## Validating a file

```bash
pip install linkml   # provides jsonschema + pyyaml too
python3 schema/validate_pals.py examples/fodo.expanded.pals.yaml
```

The validator accepts files in the PALS wire format (single-key named
entries, `- drift1: {kind: Drift, ...}`). It normalizes names, generates a
closed JSON Schema from the LinkML schema, opens `MetaP` (which may hold
arbitrary custom metadata per the standard), and reports every violation
with its document path. Unknown keys anywhere else — typos included — are
errors.

Negative examples that must fail are under `examples/invalid/`.

## Wire format vs. normalized form

PALS serializes named entries as ordered lists of single-key mappings, and
names need not be unique. That shape is not expressible in LinkML's
instance model, so the schema describes the equivalent **normalized** form
in which every entry carries an explicit `name` field. The transformation
is purely mechanical and lossless:

```bash
python3 schema/normalize_names.py examples/fodo.expanded.pals.yaml fodo.normalized.yaml
python3 schema/normalize_names.py --denormalize fodo.normalized.yaml fodo.wire.yaml
```

Normalized files can be validated directly with stock LinkML tooling:

```bash
linkml-validate -s schema/pals-expanded.linkml.yaml -C PalsFile fodo.normalized.yaml
```

(Stock `linkml-validate` treats every class as closed, so files using
custom `MetaP` keys need `validate_pals.py` instead.)

## Generating artifacts

```bash
# JSON Schema (for validators in any language)
gen-json-schema --closed schema/pals-expanded.linkml.yaml > pals-expanded.schema.json

# Pydantic v2 models
gen-pydantic schema/pals-expanded.linkml.yaml > pals_expanded_models.py
python3 schema/patch_gen_pydantic.py pals_expanded_models.py

# Documentation, ER diagrams, other formats: see linkml.io/linkml/generators/
gen-doc schema/pals-expanded.linkml.yaml -d docs-schema/

# Lint
linkml-lint --config schema/.linkmllint.yaml schema/pals-expanded.linkml.yaml
```

`patch_gen_pydantic.py` works around two upstream `gen-pydantic`
limitations: fields named like their class (the PALS parameter-group
convention, e.g. `ApertureP: ApertureP`) shadow the class name in
annotations, and the aperture `vertices.list` field shadows the `list`
builtin. It also opens `MetaP` (`extra="allow"`). The generated JSON
Schema needs no patching (the validator only adjusts `MetaP` openness and
the `linkml:Any` type list at run time).

## Dialect notes (normalized form vs. the standard's illustrative syntax)

* Named entries carry a `name` field instead of being single-key mappings
  (`facility`, `branches`, `elements`, `authors`, `UnionEle.elements` —
  the latter is a name-keyed mapping on the wire).
* Taylor series are lists of `{coef, exponents: [e1..e6]}` objects instead
  of `term <coef> <e1> ... <e6>` lines (which are not valid YAML).
* Multipole orders are explicit slots for N = 0..21 (`Bn0`...`Ks21L_taper`);
  higher orders are outside what the schema can validate.
* "Not set" is expressed by omitting a key rather than writing `null`.
  `Inf`/`-Inf` are legal PALS but not representable in JSON Schema.

## Constraints beyond structure

Enforced by the schema: required `name`/`kind`/`to_line`/`ForkP`-on-`Fork`,
name lexical rules, all enums, zero-length element kinds (BeamBeam,
BeginningEle, Fiducial, Fork, Marker, Match, Taylor), per-kind allowed
parameter groups (closed classes), `Placeholder` rejection (no such class
in the expanded form), and the documented mutual exclusions
(aperture min/max vs. center/width; RFP frequency/harmon and
voltage/gradient; ReferenceChangeP one-of groups) via LinkML rules.

Documented only (not machine-enforceable structurally): BeginningEle
first/unique and Marker last per branch, s-ordering of elements, Fork
destination-kind restriction, ReferenceP being output-only off
BeginningEle, `L_active` defaulting to the element length, same-type
constraints between multipole strength components of one order, and
multipass physical-element-set grouping / root-branch marking (the
standard defines no serialized form for these).

## Open questions flagged upstream

* **CrabCavity**: the prose calls it a "zero length RF cavity" but states
  no must-be-zero rule, and its parameter-group list omits `RFP` although
  its example uses it. The schema includes `RFP` and leaves the length
  unconstrained.
* **TwissP / ParticleP** are documented but attached to no element kind;
  the schema defines the classes without attaching them.
* **ElectricMultipoleP `geometry`** appears only in the standard's example,
  not in its component table; the schema includes it.
* **ReferenceChangeP `extra_dtime_ref`** is referenced in prose
  (patch.md, referencechange.md) but missing from the component table;
  the schema includes it.
