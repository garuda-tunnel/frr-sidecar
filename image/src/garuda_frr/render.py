"""FRR config renderer for garuda-tunnel frr-sidecar.

Renders /etc/frr/frr.conf. Called by garuda-frr-entrypoint (which calls
render_all_from_env()) or as a standalone CLI (garuda-frr-render).

Inputs (in priority order):
  1. Env vars injected by MAP: OSPF_INTERFACES, OSPF_PASSIVE_INTERFACES,
     REDISTRIBUTE, OSPF_ROUTER_ID, PROFILE, PBR_TRANSIT_TAG,
     PBR_TRANSIT_INTERFACES.
  2. Intent annotation file at INTENT_MOUNT/annotations (Downward API).
     Annotation values override env vars for the same logical field. The
     net.garuda-tunnel/passive-interfaces annotation (CSV) maps to
     OSPF_PASSIVE_INTERFACES; those interfaces render as passive (area +
     `ip ospf passive`, no hello/dead timers, no mtu-ignore) and are excluded
     from the active OSPF_INTERFACES timer stanzas.
  3. Profile template at PROFILE_MOUNT/frr.conf.tmpl.
  4. Tier 2 snippet at EXTRA_MOUNT/ (appended if dir exists).
  5. Tier 3 raw override at RAW_MOUNT/ (bypasses template if dir exists AND
     net.garuda-tunnel/frr-mode=raw annotation is set).

Mount path env vars (with defaults matching MAP injection):
  PROFILE_MOUNT   default _DEFAULT_PROFILE_MOUNT (/etc/garuda/profile)
  INTENT_MOUNT    default _DEFAULT_INTENT_MOUNT  (/etc/garuda/intent)
  EXTRA_MOUNT     default _DEFAULT_EXTRA_MOUNT   (/etc/garuda/extra, optional; Tier 2)
  RAW_MOUNT       default _DEFAULT_RAW_MOUNT     (/etc/garuda/raw,   optional; Tier 3)

Default paths are defined as module constants (_DEFAULT_*_MOUNT) and used
as os.environ.get() fallbacks in main(). The chart template _container.tpl
mountPath entries must match these defaults — see the comment there.

Template placeholders supported:
  ${ROUTER_ID}               — OSPF router-id
  ${OSPF_INTERFACES_BLOCK}   — per-interface stanzas
  ${REDISTRIBUTE_BLOCK}      — redistribute directives
  ${DEFAULT_ORIGINATE_BLOCK} — default-information originate (or empty)

BACKBONE_IP is extracted by garuda-frr-entrypoint via `ip -j addr show backbone`
and exported to the environment. It is NOT a template placeholder and is not
processed by this module.

Python stdlib only. No Jinja2, no envsubst, no gomplate.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from string import Template

import click

from garuda_frr.utils import csv_split

# ---------------------------------------------------------------------------
# Mount path defaults — single source of truth.
# Chart template _container.tpl mountPath entries must match these values;
# see charts/frr-sidecar/templates/_container.tpl comment near mountPaths.
# ---------------------------------------------------------------------------

_DEFAULT_PROFILE_MOUNT = "/etc/garuda/profile"
_DEFAULT_INTENT_MOUNT = "/etc/garuda/intent"
_DEFAULT_EXTRA_MOUNT = "/etc/garuda/extra"
_DEFAULT_RAW_MOUNT = "/etc/garuda/raw"

# ---------------------------------------------------------------------------
# Input validation — regexes and allowlist
# ---------------------------------------------------------------------------

_ROUTER_ID_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
_IFACE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,15}$")
_REDISTRIBUTE_ALLOWLIST = frozenset(
    {"kernel", "connected", "static", "bgp", "rip", "isis"}
)


def validate_router_id(value: str) -> str:
    """Raise ValueError if value is not an IPv4 dotted-quad string."""
    if not _ROUTER_ID_RE.match(value):
        raise ValueError(f"invalid router-id (must be IPv4 dotted-quad): {value!r}")
    return value


def validate_interfaces(names: list[str]) -> list[str]:
    """Raise ValueError if any interface name violates Linux naming rules."""
    for n in names:
        if not _IFACE_NAME_RE.match(n):
            raise ValueError(
                f"invalid interface name (Linux iface naming rules): {n!r}"
            )
    return names


def validate_redistribute(protos: list[str]) -> list[str]:
    """Raise ValueError if any redistribute protocol is not in the allowlist."""
    for p in protos:
        if p not in _REDISTRIBUTE_ALLOWLIST:
            raise ValueError(
                f"invalid redistribute protocol {p!r}; "
                f"allowed: {sorted(_REDISTRIBUTE_ALLOWLIST)}"
            )
    return protos


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_annotations(content: str) -> dict[str, str]:
    """Parse a Downward API annotations file into a dict.

    The Downward API annotations file format is one key=value pair per line,
    with the value double-quoted:
        net.garuda-tunnel/router-id="10.130.30.22"
        kubernetes.io/config.source="api"

    Returns only the net.garuda-tunnel/* keys with quotes stripped.
    """
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if "=" not in line:
            continue
        key, _, raw_val = line.partition("=")
        key = key.strip()
        raw_val = raw_val.strip()
        if not key.startswith("net.garuda-tunnel/"):
            continue
        # Strip surrounding double-quotes produced by the Downward API
        if raw_val.startswith('"') and raw_val.endswith('"'):
            raw_val = raw_val[1:-1]
        result[key] = raw_val
    return result


def render_ospf_interfaces(interfaces: list[str]) -> str:
    """Render per-interface FRR stanzas for ACTIVE OSPF interfaces.

    For each interface name produces (prod-parity, frr-sidecar 0.2.x ground truth):
        interface <name>
          ip ospf area 0.0.0.0
          ip ospf hello-interval 5
          ip ospf dead-interval 15
          ip ospf mtu-ignore
        !

    The hello/dead timers (5s/15s) are mandatory: the production OSPF mesh runs
    Hello 5s / Dead 15s. Omitting them lets FRR fall back to 10s/40s, which
    prevents adjacency formation entirely (timer mismatch -> hellos rejected).
    See docs/artifacts/2026-06-25-vxxlcx-prod-frr-ground-truth.md (D1/D2).
    """
    if not interfaces:
        return ""
    lines = []
    for iface in interfaces:
        lines += [
            f"interface {iface}",
            "  ip ospf area 0.0.0.0",
            "  ip ospf hello-interval 5",
            "  ip ospf dead-interval 15",
            "  ip ospf mtu-ignore",
            "!",
        ]
    return "\n".join(lines)


def render_passive_interfaces(interfaces: list[str]) -> str:
    """Render per-interface FRR stanzas for PASSIVE OSPF interfaces.

    For each interface name produces (prod-parity, frr-sidecar 0.2.x ground truth
    — firezone wg-firezone, border dummy0):
        interface <name>
          ip ospf area 0.0.0.0
          ip ospf passive
        !

    Passive interfaces participate in OSPF (their subnet is advertised) but send
    NO hellos and form NO adjacency. Production renders them with area + passive
    ONLY — no hello/dead timers and NO mtu-ignore (mtu-ignore is moot on a passive
    interface and is absent in the prod ground-truth raw frr.conf). See
    docs/artifacts/2026-06-25-vxxlcx-prod-frr-ground-truth.md §2.5/§2.6 (D11).
    """
    if not interfaces:
        return ""
    lines = []
    for iface in interfaces:
        lines += [
            f"interface {iface}",
            "  ip ospf area 0.0.0.0",
            "  ip ospf passive",
            "!",
        ]
    return "\n".join(lines)


def render_interface_block(
    active: list[str], passive: list[str] | None = None
) -> str:
    """Render the combined OSPF interface block: active stanzas then passive.

    Active interfaces (with timers + mtu-ignore) are emitted first, followed by
    passive interfaces (area + passive only). This ordering matches the prod
    ground truth (active backbone/tunnel first, then passive wg-firezone/dummy0).
    """
    passive = passive or []
    parts = []
    active_block = render_ospf_interfaces(active)
    if active_block:
        parts.append(active_block)
    passive_block = render_passive_interfaces(passive)
    if passive_block:
        parts.append(passive_block)
    return "\n".join(parts)


def render_redistribute(protocols: list[str]) -> str:
    """Render `redistribute <proto>` lines for inside a router ospf block.

    Each entry is rendered at column 0; the profile template places this block
    via `  ${REDISTRIBUTE_BLOCK}` (2-space indent), so the directive lands as a
    `router ospf` sub-command. Emitting 0-indent here (rather than the previous
    2-space indent) avoids the double-indent that made ospfd silently drop the
    directive. See docs/artifacts/2026-06-24-frr-conf-old-vs-new-diff.md (D3).
    """
    if not protocols:
        return ""
    return "\n".join(f"redistribute {p}" for p in protocols)


def render_default_originate(value: str) -> str:
    """Return `  default-information originate` when value is 'true', else ''."""
    if value.lower() == "true":
        return "  default-information originate"
    return ""


def render_from_template(
    *,
    template: str,
    router_id: str,
    interfaces: list[str],
    redistribute: list[str],
    default_originate: str,
    passive_interfaces: list[str] | None = None,
) -> str:
    """Substitute all garuda placeholders in the FRR config template.

    Placeholder tokens:
        ${ROUTER_ID}              — OSPF router-id
        ${OSPF_INTERFACES_BLOCK}  — per-interface stanzas (active then passive)
        ${REDISTRIBUTE_BLOCK}     — redistribute directives
        ${DEFAULT_ORIGINATE_BLOCK}— default-information originate (or empty)

    The ${OSPF_INTERFACES_BLOCK} renders active interfaces (with hello/dead
    timers + mtu-ignore) followed by passive interfaces (area + passive only).

    Uses string.Template.safe_substitute for single-pass substitution;
    unknown placeholders are left verbatim (not raised as errors).
    """
    return Template(template).safe_substitute(
        ROUTER_ID=router_id,
        OSPF_INTERFACES_BLOCK=render_interface_block(interfaces, passive_interfaces),
        REDISTRIBUTE_BLOCK=render_redistribute(redistribute),
        DEFAULT_ORIGINATE_BLOCK=render_default_originate(default_originate),
    )


def apply_tier2_snippet(base_config: str, extra_mount: str) -> str:
    """Append Tier 2 FRR snippet files to base_config if extra_mount exists.

    Reads all files in extra_mount/ in sorted order and appends their content
    separated by a newline. Returns base_config unchanged when the directory
    does not exist or is empty.
    """
    extra_path = Path(extra_mount)
    if not extra_path.is_dir():
        return base_config
    snippets = sorted(extra_path.iterdir())
    if not snippets:
        return base_config
    parts = [base_config]
    for snippet in snippets:
        if snippet.is_file():
            parts.append(snippet.read_text())
    return "\n".join(parts)


def load_raw_config(raw_mount: str) -> str | None:
    """Return content of the raw FRR config file, or None if raw_mount absent.

    Looks for `frr.conf` inside raw_mount. Returns None when the directory
    does not exist (Tier 3 not active).
    """
    raw_path = Path(raw_mount)
    if not raw_path.is_dir():
        return None
    raw_file = raw_path / "frr.conf"
    if raw_file.exists():
        return raw_file.read_text()
    return None


def render_all_from_env() -> str:
    """Render FRR config from environment and return as string.

    Extracted from main() so entrypoint can call directly without subprocess.
    Priority for interface/redistribute/router-id:
      - Annotation value (from intent file) takes precedence over env var.
      - Env var is used as fallback when annotation key is absent.

    Raises SystemExit(1) on fatal errors (missing template, validation failure).
    """
    profile_mount = os.environ.get("PROFILE_MOUNT", _DEFAULT_PROFILE_MOUNT)
    intent_mount = os.environ.get("INTENT_MOUNT", _DEFAULT_INTENT_MOUNT)
    extra_mount = os.environ.get("EXTRA_MOUNT", _DEFAULT_EXTRA_MOUNT)
    raw_mount = os.environ.get("RAW_MOUNT", _DEFAULT_RAW_MOUNT)

    # --- Read intent annotations (Downward API file) ---
    intent_file = Path(intent_mount) / "annotations"
    annotations: dict[str, str] = {}
    if intent_file.exists():
        annotations = parse_annotations(intent_file.read_text())

    frr_mode = annotations.get("net.garuda-tunnel/frr-mode", "")

    # --- Tier 3: raw override ---
    if frr_mode == "raw":
        raw_config = load_raw_config(raw_mount)
        if raw_config is not None:
            return raw_config
        print(
            "FATAL: frr-mode=raw but RAW_MOUNT has no frr.conf. "
            "Fix the raw ConfigMap and trigger a rolling update.",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Resolve config values: annotation > env var ---
    router_id = annotations.get("net.garuda-tunnel/router-id") or os.environ.get(
        "OSPF_ROUTER_ID", ""
    )
    interfaces_raw = annotations.get("net.garuda-tunnel/interfaces") or os.environ.get(
        "OSPF_INTERFACES", ""
    )
    redistribute_raw = annotations.get(
        "net.garuda-tunnel/redistribute"
    ) or os.environ.get("REDISTRIBUTE", "")
    default_originate = annotations.get(
        "net.garuda-tunnel/default-originate"
    ) or os.environ.get("DEFAULT_ORIGINATE", "false")
    passive_raw = annotations.get(
        "net.garuda-tunnel/passive-interfaces"
    ) or os.environ.get("OSPF_PASSIVE_INTERFACES", "")

    interfaces = csv_split(interfaces_raw)
    redistribute = csv_split(redistribute_raw)
    passive_interfaces = csv_split(passive_raw)

    # Passive interfaces are rendered as their own (area + passive) stanzas;
    # remove them from the active set so they are not emitted twice (a passive
    # iface listed in both net.garuda-tunnel/interfaces and /passive-interfaces
    # would otherwise produce a duplicate interface block).
    interfaces = [i for i in interfaces if i not in passive_interfaces]

    # --- Validate untrusted inputs before substitution ---
    try:
        validate_router_id(router_id)
        validate_interfaces(interfaces)
        validate_interfaces(passive_interfaces)
        validate_redistribute(redistribute)
    except ValueError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Load profile template ---
    template_file = Path(profile_mount) / "frr.conf.tmpl"
    if not template_file.exists():
        print(
            f"FATAL: profile template not found at {template_file}. "
            "Ensure the garuda-profile ConfigMap is mounted at PROFILE_MOUNT.",
            file=sys.stderr,
        )
        sys.exit(1)
    template = template_file.read_text()

    # --- Render ---
    config = render_from_template(
        template=template,
        router_id=router_id,
        interfaces=interfaces,
        redistribute=redistribute,
        default_originate=default_originate,
        passive_interfaces=passive_interfaces,
    )

    # --- Tier 2: append extra snippet ---
    config = apply_tier2_snippet(config, extra_mount)

    return config


def main() -> None:
    """Render FRR config to stdout.

    Called by garuda-frr-render CLI entry point or directly for testing.
    """
    config = render_all_from_env()
    print(config, end="")


@click.command()
@click.option(
    "--profile-mount",
    envvar="PROFILE_MOUNT",
    default=_DEFAULT_PROFILE_MOUNT,
    show_default=True,
    help="Path to the profile ConfigMap mount (frr.conf.tmpl).",
)
@click.option(
    "--intent-mount",
    envvar="INTENT_MOUNT",
    default=_DEFAULT_INTENT_MOUNT,
    show_default=True,
    help="Path to the Downward API intent annotations mount.",
)
@click.option(
    "--extra-mount",
    envvar="EXTRA_MOUNT",
    default=_DEFAULT_EXTRA_MOUNT,
    show_default=True,
    help="Path to the Tier 2 extra snippet mount (optional).",
)
@click.option(
    "--raw-mount",
    envvar="RAW_MOUNT",
    default=_DEFAULT_RAW_MOUNT,
    show_default=True,
    help="Path to the Tier 3 raw config mount (optional).",
)
@click.option(
    "--print-only",
    is_flag=True,
    default=False,
    help="Print rendered config to stdout instead of writing /etc/frr/frr.conf.",
)
def cli(
    profile_mount: str,
    intent_mount: str,
    extra_mount: str,
    raw_mount: str,
    print_only: bool,
) -> None:
    """garuda-frr-render: render frr.conf from profile template and intent annotations."""
    import os as _os

    _os.environ.setdefault("PROFILE_MOUNT", profile_mount)
    _os.environ.setdefault("INTENT_MOUNT", intent_mount)
    _os.environ.setdefault("EXTRA_MOUNT", extra_mount)
    _os.environ.setdefault("RAW_MOUNT", raw_mount)

    config = render_all_from_env()
    if print_only:
        click.echo(config, nl=False)
    else:
        Path("/etc/frr/frr.conf").write_text(config)
        click.echo("garuda-frr-render: wrote /etc/frr/frr.conf", err=True)


if __name__ == "__main__":
    main()
