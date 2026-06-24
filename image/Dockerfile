FROM quay.io/frrouting/frr:10.6.0

# FRR sidecar image for garuda-tunnel annotation-layer model.
# Configuration is rendered at container startup by garuda-frr-entrypoint from:
#   - Profile ConfigMap mount at /etc/garuda/profile/ (frr.conf.tmpl, daemons)
#   - Intent annotations via Downward API at /etc/garuda/intent/annotations
#   - Env vars injected by MAP (OSPF_INTERFACES, REDISTRIBUTE, OSPF_ROUTER_ID,
#     PROFILE, PBR_TRANSIT_TAG, PBR_TRANSIT_INTERFACES).

# Install Python and pip, then install garuda-frr as a proper package.
# --break-system-packages: this image has no virtualenv; the container IS the
# isolation boundary. We install into the system Python intentionally.
RUN apk add --no-cache python3 py3-pip

COPY src /opt/garuda-frr/src
COPY pyproject.toml /opt/garuda-frr/pyproject.toml
RUN pip3 install --no-cache-dir --break-system-packages /opt/garuda-frr/

# Entrypoint renders frr.conf at runtime to /etc/frr/frr.conf as root.
# /etc/frr is frr:frr 0755 in the base image; with capabilities drop:ALL the
# root process loses DAC_OVERRIDE and cannot write there. Make the directory
# root-owned so root writes its own files without DAC_OVERRIDE, keeping the
# historical minimal cap set (NET_ADMIN/NET_RAW/SYS_ADMIN). daemons stays readable.
RUN chown root:root /etc/frr

ENTRYPOINT ["garuda-frr-entrypoint"]
