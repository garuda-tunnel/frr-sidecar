FROM quay.io/frrouting/frr:10.6.0

# FRR sidecar image for OSPF injector operator.
# Configuration is delivered via base64-encoded environment variables
# (FRR_CONF_B64, DAEMONS_B64, VTYSH_CONF_B64) instead of file bind-mounts.

RUN apk add --no-cache python3 py3-pip \
    && pip3 install --no-cache-dir --break-system-packages \
       'pyroute2>=0.7.12' 'flask>=3.0' 'waitress>=3.0'

COPY transit_watcher.py /usr/lib/frr/transit_watcher.py
COPY vtysh_client.py /usr/lib/frr/vtysh_client.py
COPY vty_bridge.py /usr/lib/frr/vty_bridge.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
