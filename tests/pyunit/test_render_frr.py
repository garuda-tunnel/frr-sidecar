"""Unit tests for garuda_frr.render — FRR config renderer.

Tests are written first (TDD). Run with:
    pytest tests/pyunit/test_render_frr.py -v
from the frr-sidecar-internal/ directory.

conftest.py adds frr-sidecar-internal/image/src/ to sys.path so garuda_frr
is importable.
"""

from __future__ import annotations

import os

import pytest

import garuda_frr.render as render_frr

# ---------------------------------------------------------------------------
# 1. Intent annotation file parsing
# ---------------------------------------------------------------------------


SAMPLE_ANNOTATIONS = """\
net.garuda-tunnel/profile="ospf-router"
net.garuda-tunnel/router-id="10.130.30.22"
net.garuda-tunnel/interfaces="backbone,wg0"
net.garuda-tunnel/redistribute="connected,kernel"
net.garuda-tunnel/default-originate="false"
kubernetes.io/config.source="api"
"""


def test_parse_annotations_extracts_garuda_keys():
    """parse_annotations returns a dict of all net.garuda-tunnel/* key→value pairs."""
    result = render_frr.parse_annotations(SAMPLE_ANNOTATIONS)
    assert result["net.garuda-tunnel/router-id"] == "10.130.30.22"
    assert result["net.garuda-tunnel/interfaces"] == "backbone,wg0"
    assert result["net.garuda-tunnel/redistribute"] == "connected,kernel"
    assert result["net.garuda-tunnel/default-originate"] == "false"


def test_parse_annotations_ignores_non_garuda_keys():
    """parse_annotations does not include kubernetes.io/* keys."""
    result = render_frr.parse_annotations(SAMPLE_ANNOTATIONS)
    assert "kubernetes.io/config.source" not in result


def test_parse_annotations_empty_string():
    """parse_annotations returns empty dict for empty input."""
    assert render_frr.parse_annotations("") == {}


def test_parse_annotations_missing_key():
    """parse_annotations returns empty dict when no garuda keys present."""
    result = render_frr.parse_annotations('kubernetes.io/x="y"')
    assert result == {}


# ---------------------------------------------------------------------------
# 2. CSV split helper
# ---------------------------------------------------------------------------


def test_csv_split_normal():
    assert render_frr.csv_split("backbone,wg0") == ["backbone", "wg0"]


def test_csv_split_single():
    assert render_frr.csv_split("backbone") == ["backbone"]


def test_csv_split_empty_string():
    """csv_split of empty string returns empty list."""
    assert render_frr.csv_split("") == []


def test_csv_split_strips_whitespace():
    assert render_frr.csv_split("backbone, wg0 , eth0") == ["backbone", "wg0", "eth0"]


# ---------------------------------------------------------------------------
# 3. render_ospf_interfaces — per-interface stanzas
# ---------------------------------------------------------------------------


def test_render_ospf_interfaces_multiple():
    """render_ospf_interfaces produces one stanza block per interface."""
    result = render_frr.render_ospf_interfaces(["backbone", "wg0"])
    assert "interface backbone" in result
    assert "interface wg0" in result
    assert result.count("ip ospf area 0.0.0.0") == 2


def test_render_ospf_interfaces_empty():
    """render_ospf_interfaces returns empty string for empty list."""
    assert render_frr.render_ospf_interfaces([]) == ""


# ---------------------------------------------------------------------------
# 4. render_redistribute — redistribute stanzas
# ---------------------------------------------------------------------------


def test_render_redistribute_multiple():
    result = render_frr.render_redistribute(["connected", "kernel"])
    assert "  redistribute connected" in result
    assert "  redistribute kernel" in result


def test_render_redistribute_empty():
    assert render_frr.render_redistribute([]) == ""


# ---------------------------------------------------------------------------
# 5. render_default_originate
# ---------------------------------------------------------------------------


def test_render_default_originate_true():
    result = render_frr.render_default_originate("true")
    assert "default-information originate" in result


def test_render_default_originate_false():
    assert render_frr.render_default_originate("false") == ""


def test_render_default_originate_missing():
    assert render_frr.render_default_originate("") == ""


# ---------------------------------------------------------------------------
# 6. render_from_template — full template substitution
# ---------------------------------------------------------------------------

SAMPLE_TEMPLATE = """\
frr defaults traditional
log file /tmp/frr.log
zebra nexthop proto only
!
router ospf
  ospf router-id ${ROUTER_ID}
  ${OSPF_INTERFACES_BLOCK}
  ${REDISTRIBUTE_BLOCK}
  ${DEFAULT_ORIGINATE_BLOCK}
!
"""


def test_render_from_template_full():
    """render_from_template substitutes all placeholders correctly."""
    config = render_frr.render_from_template(
        template=SAMPLE_TEMPLATE,
        router_id="10.130.30.22",
        interfaces=["backbone", "wg0"],
        redistribute=["connected"],
        default_originate="false",
    )
    assert "ospf router-id 10.130.30.22" in config
    assert "interface backbone" in config
    assert "interface wg0" in config
    assert "redistribute connected" in config
    assert "default-information originate" not in config
    # placeholders must not appear in output
    assert "${ROUTER_ID}" not in config
    assert "${OSPF_INTERFACES_BLOCK}" not in config
    assert "${REDISTRIBUTE_BLOCK}" not in config
    assert "${DEFAULT_ORIGINATE_BLOCK}" not in config


def test_render_from_template_with_default_originate():
    config = render_frr.render_from_template(
        template=SAMPLE_TEMPLATE,
        router_id="10.130.30.10",
        interfaces=["backbone"],
        redistribute=[],
        default_originate="true",
    )
    assert "default-information originate" in config


# ---------------------------------------------------------------------------
# 7. Tier 2 — extra snippet append
# ---------------------------------------------------------------------------


def test_apply_tier2_snippet_appends(tmp_path):
    """apply_tier2_snippet appends file content to base config when dir exists."""
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    (extra_dir / "snippet.conf").write_text(
        "! custom route-map\nroute-map CUSTOM permit 10\n"
    )

    base = "! base config\n"
    result = render_frr.apply_tier2_snippet(base, str(extra_dir))
    assert "! base config" in result
    assert "route-map CUSTOM permit 10" in result


def test_apply_tier2_snippet_absent_dir(tmp_path):
    """apply_tier2_snippet returns base unchanged when extra dir does not exist."""
    base = "! base config\n"
    result = render_frr.apply_tier2_snippet(base, str(tmp_path / "nonexistent"))
    assert result == base


# ---------------------------------------------------------------------------
# 8. Tier 3 — raw override
# ---------------------------------------------------------------------------


def test_load_raw_config_present(tmp_path):
    """load_raw_config returns content of the raw configmap file when present."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_conf = "frr defaults traditional\n! raw override\n"
    (raw_dir / "frr.conf").write_text(raw_conf)

    result = render_frr.load_raw_config(str(raw_dir))
    assert result == raw_conf


def test_load_raw_config_absent(tmp_path):
    """load_raw_config returns None when raw dir does not exist."""
    result = render_frr.load_raw_config(str(tmp_path / "nonexistent"))
    assert result is None


# ---------------------------------------------------------------------------
# 9. main() integration — env-driven end-to-end
# ---------------------------------------------------------------------------


def test_main_renders_full_config(profile_dir_builder, monkeypatch, capsys):
    """render_frr.main() prints a valid FRR config block to stdout."""
    dirs = profile_dir_builder(
        template=SAMPLE_TEMPLATE,
        annotations=(
            'net.garuda-tunnel/router-id="10.130.30.22"\n'
            'net.garuda-tunnel/interfaces="backbone,wg0"\n'
            'net.garuda-tunnel/redistribute="connected"\n'
            'net.garuda-tunnel/default-originate="false"\n'
        ),
    )
    env = {
        "BACKBONE_IP": "172.30.0.5",
        "PROFILE": "ospf-router",
        "OSPF_INTERFACES": "",  # overridden by annotation
        "REDISTRIBUTE": "",  # overridden by annotation
        "PBR_TRANSIT_TAG": "",
        "PBR_TRANSIT_INTERFACES": "",
        **dirs["env"],
    }
    monkeypatch.setattr(os, "environ", {**os.environ, **env})

    render_frr.main()
    out = capsys.readouterr().out
    assert "ospf router-id 10.130.30.22" in out
    assert "interface backbone" in out
    assert "interface wg0" in out
    assert "redistribute connected" in out


def test_main_tier3_raw_bypasses_template(profile_dir_builder, monkeypatch, capsys):
    """render_frr.main() emits raw config verbatim when /etc/garuda/raw/ is present."""
    raw_conf = "! fully raw frr config\nfrr defaults traditional\n"
    dirs = profile_dir_builder(
        template=SAMPLE_TEMPLATE,
        annotations=(
            'net.garuda-tunnel/router-id="10.130.30.22"\n'
            'net.garuda-tunnel/frr-mode="raw"\n'
        ),
        raw_conf=raw_conf,
    )
    env = {
        "BACKBONE_IP": "172.30.0.5",
        "PROFILE": "ospf-router",
        "OSPF_INTERFACES": "",
        "REDISTRIBUTE": "",
        "PBR_TRANSIT_TAG": "",
        "PBR_TRANSIT_INTERFACES": "",
        **dirs["env"],
    }
    monkeypatch.setattr(os, "environ", {**os.environ, **env})

    render_frr.main()
    out = capsys.readouterr().out
    assert "fully raw frr config" in out
    # template markers must not appear
    assert "${ROUTER_ID}" not in out


# ---------------------------------------------------------------------------
# 10. Input validation — validate_router_id, validate_interfaces,
#     validate_redistribute, and safe_substitute cross-expansion resistance
# ---------------------------------------------------------------------------


def test_validate_router_id_valid():
    """validate_router_id accepts a proper IPv4 dotted-quad."""
    assert render_frr.validate_router_id("10.130.30.22") == "10.130.30.22"


def test_validate_router_id_invalid():
    """validate_router_id raises ValueError for non-dotted-quad strings."""
    with pytest.raises(ValueError, match="invalid router-id"):
        render_frr.validate_router_id("not.an.ip")


def test_validate_interfaces_valid():
    """validate_interfaces accepts valid Linux interface names."""
    assert render_frr.validate_interfaces(["wg0", "backbone"]) == ["wg0", "backbone"]


def test_validate_interfaces_invalid():
    """validate_interfaces raises ValueError for names with spaces."""
    with pytest.raises(ValueError, match="invalid interface name"):
        render_frr.validate_interfaces(["wg 0"])


def test_validate_redistribute_valid():
    """validate_redistribute accepts protocol names from the allowlist."""
    assert render_frr.validate_redistribute(["kernel", "connected"]) == [
        "kernel",
        "connected",
    ]


def test_validate_redistribute_invalid():
    """validate_redistribute raises ValueError for unlisted protocol names."""
    with pytest.raises(ValueError, match="invalid redistribute protocol"):
        render_frr.validate_redistribute(["bogus"])


def test_render_from_template_safe_substitute_no_cross_expansion():
    """safe_substitute does not double-expand substituted values.

    With sequential str.replace(), a router_id containing '${OSPF_INTERFACES_BLOCK}'
    would be re-expanded in a later replace() call. Template.safe_substitute performs
    a single pass: the value injected for ROUTER_ID is treated as a literal string
    and the OSPF_INTERFACES_BLOCK in the original template is independently replaced.
    """
    # Template has both ROUTER_ID and OSPF_INTERFACES_BLOCK placeholders
    tmpl = "router-id ${ROUTER_ID}\nblock: ${OSPF_INTERFACES_BLOCK}"
    # router_id value happens to look like another placeholder
    result = render_frr.render_from_template(
        template=tmpl,
        router_id="${OSPF_INTERFACES_BLOCK}",
        interfaces=[],
        redistribute=[],
        default_originate="false",
    )
    # The ROUTER_ID slot is filled with the literal string (single-pass, not re-expanded)
    assert "router-id ${OSPF_INTERFACES_BLOCK}" in result
    # The original OSPF_INTERFACES_BLOCK placeholder on its own line is substituted
    # to empty (no interfaces) — "block: " remains with empty trailing content
    assert "block: " in result
    # Total occurrence of ${OSPF_INTERFACES_BLOCK} is exactly 1 (from router_id value),
    # confirming the original template placeholder was consumed (single-pass semantics).
    assert result.count("${OSPF_INTERFACES_BLOCK}") == 1
