#!/usr/bin/env python3
"""Post-process the output of ``gen-pydantic pals-expanded.linkml.yaml``.

PALS keys each parameter group by the group's own name (``ApertureP:
{...}``), so the generated pydantic models contain fields whose name
equals their annotation's class name (``ApertureP: Optional[ApertureP]``).
Inside a pydantic class body the field assignment shadows the class name,
so pydantic cannot evaluate such annotations (and silently disables
validation where it can). Similarly, the aperture ``vertices.list``
component shadows the ``list`` builtin.

This is an upstream gen-pydantic limitation, not a schema defect; the
generated JSON Schema is unaffected. This script rewrites the generated
module so all annotations resolve:

  * ``_Group_<Name> = <Name>`` aliases are inserted after the parameter
    group class definitions, and group-named fields are re-annotated to
    use the alias.
  * ``Optional[list[...]]`` inside the class defining a ``list`` field is
    rewritten to ``Optional[List[...]]`` (with the required import).
  * ``MetaP`` is opened (``extra="allow"``): per the standard it may hold
    arbitrary custom metadata beyond its six standard components, which
    LinkML cannot express per-class.

Usage:
    gen-pydantic pals-expanded.linkml.yaml > pals_expanded_models.py
    python3 patch_gen_pydantic.py pals_expanded_models.py
"""

import re
import sys


def patch(src: str) -> str:
    # Parameter-group classes: generated classes named like the PALS
    # groups (upper camel case ending in "P").
    group_names = [
        m.group(1)
        for m in re.finditer(r"^class ([A-Z]\w*P)\(", src, re.M)
    ]
    if not group_names:
        raise SystemExit("no parameter-group classes found; wrong input?")

    # 1. Alias the group classes before the element hierarchy begins.
    anchor = "class LatticeElement("
    if anchor not in src:
        raise SystemExit("LatticeElement class not found; wrong input?")
    aliases = (
        "# Aliases so that fields named like their class (PALS parameter\n"
        "# groups) do not shadow the class name in annotations.\n"
        + "".join(f"_Group_{g} = {g}\n" for g in group_names)
        + "\n\n"
    )
    src = src.replace(anchor, aliases + anchor, 1)

    # 2. Re-annotate fields whose name equals the annotation class name.
    for g in group_names:
        src = re.sub(
            rf"^(\s+{g}): (Optional\[)?{g}(\]?) = Field\(",
            rf"\1: \g<2>_Group_{g}\3 = Field(",
            src,
            flags=re.M,
        )

    # 3. Fields named ``list`` shadow the builtin within their class;
    #    switch sibling annotations to typing.List there.
    lines = src.split("\n")
    shadowed_classes = set()
    current = None
    for line in lines:
        m = re.match(r"^class (\w+)\(", line)
        if m:
            current = m.group(1)
        elif re.match(r"^\s+list\s*:", line) and current:
            shadowed_classes.add(current)
    if shadowed_classes:
        out = []
        current = None
        for line in lines:
            m = re.match(r"^class (\w+)\(", line)
            if m:
                current = m.group(1)
            if current in shadowed_classes:
                line = line.replace("Optional[list[", "Optional[List[")
            out.append(line)
        src = "\n".join(out)
        src = src.replace(
            "from typing import (",
            "from typing import List\nfrom typing import (",
            1,
        )

    # 4. MetaP may hold arbitrary custom metadata (open class).
    src = src.replace(
        "class MetaP(ConfiguredBaseModel):",
        'class MetaP(ConfiguredBaseModel):\n    model_config = ConfigDict(extra="allow")\n',
        1,
    )

    return src


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    path = sys.argv[1]
    with open(path) as f:
        src = f.read()
    src = patch(src)
    with open(path, "w") as f:
        f.write(src)
    print(f"patched {path}")


if __name__ == "__main__":
    main()
