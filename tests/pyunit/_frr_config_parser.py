"""Semantic FRR-config assertions via ciscoconfparse2.

FRR follows Cisco IOS indent-hierarchical syntax, which ciscoconfparse2
parses natively. This module exposes a thin query surface over the
parser so rendering tests can assert on *meaning* (does this interface
block declare area 0.0.0.0? is this route-map set with tag 201?) rather
than on line-by-line whitespace that Jinja or string-concat rendering
might format slightly differently.

Public functions return plain Python types (lists of str, bools, etc.)
so test assertions stay readable and do not leak ciscoconfparse2 types.
"""

from __future__ import annotations

from ciscoconfparse2 import CiscoConfParse


def parse_frr(text: str) -> CiscoConfParse:
    """Parse rendered FRR config text into a CiscoConfParse tree."""
    return CiscoConfParse(text.splitlines())


def _children(parse: CiscoConfParse, pattern: str) -> list[str]:
    """Return stripped child text of the first object matching pattern, or []."""
    objs = parse.find_objects(pattern)
    if not objs:
        return []
    return [child.text.strip() for child in objs[0].children]


def iface_block(parse: CiscoConfParse, name: str) -> list[str]:
    """Return children of ``interface <name>`` (empty list if absent)."""
    return _children(parse, rf"^interface {name}$")


def router_ospf_block(parse: CiscoConfParse) -> list[str]:
    """Return children of the (single) ``router ospf`` block."""
    return _children(parse, r"^router ospf$")


def route_map_block(parse: CiscoConfParse, name: str) -> list[str]:
    """Return children of ``route-map <name> permit|deny <seq>`` (first match)."""
    return _children(parse, rf"^route-map {name} ")


def has_interface(parse: CiscoConfParse, name: str) -> bool:
    return bool(parse.find_objects(rf"^interface {name}$"))


def interface_names_in_order(parse: CiscoConfParse) -> list[str]:
    """Return interface names in declaration order.

    Used for assertions like 'backbone is always declared first'.
    """
    out: list[str] = []
    for obj in parse.find_objects(r"^interface "):
        text = obj.text.strip()
        # "interface <name>"
        out.append(text.split(None, 1)[1])
    return out


def iface_is_active(parse: CiscoConfParse, name: str) -> bool:
    """True when the interface block declares OSPF active timers.

    Compact-mode active interfaces get ``ip ospf hello-interval 5``,
    ``ip ospf dead-interval 15``, ``ip ospf mtu-ignore`` and do NOT
    carry ``ip ospf passive``.
    """
    block = iface_block(parse, name)
    return (
        any(line.startswith("ip ospf hello-interval") for line in block)
        and "ip ospf passive" not in block
    )


def iface_is_passive(parse: CiscoConfParse, name: str) -> bool:
    """True when the interface block declares ``ip ospf passive``."""
    block = iface_block(parse, name)
    return "ip ospf passive" in block
