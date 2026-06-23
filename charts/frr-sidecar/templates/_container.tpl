{{/*
Render the FRR/OSPF sidecar container as a single list element.

Usage (inside spec.template.spec.initContainers or spec.containers):
    {{- include "frr-sidecar.container" (dict
          "image"    .Values.images.frr
          "ospf"     .Values.ospf
          "transit"  .Values.transit
        ) | nindent 8 }}

The template is a no-op when `.ospf` is nil. Callers MUST include
unconditionally (no caller-side {{- if .Values.ospf }} wrapper).

Required dict keys:
    image:   container image reference (string; empty/omitted ⇒ frr-sidecar.defaultImage tag)
    ospf:    dict consumed by frr-sidecar.frrConf
    transit: dict with `interfaces: [string]` (optional)
    injected: bool (default false) — set true only when MAP injects
              garuda-profile and garuda-intent volumes into the pod.
              When false (legacy mode), those volumeMounts are omitted
              so consumers that call frr-sidecar.volume (which emits
              only frr-source) do not get broken volume references.
              Phase 3+ MAP-aware consumers set injected=true.

Phase 2 changes:
  - readinessProbe now targets /readyz on port 9179 (0.0.0.0 bind — kubelet reachable).
    The old /health on 127.0.0.1:7890 is NOT a valid kubelet probe target.
  - Env vars OSPF_INTERFACES, REDISTRIBUTE, OSPF_ROUTER_ID, PROFILE, BACKBONE_IP
    are passed through from .ospf dict for render_frr.py.
  - volumeMounts for /etc/garuda/profile and /etc/garuda/intent are gated on
    injected=true (MAP-aware consumers only — see injected key above).
  - Legacy frr-source mount retained for backwards compat during Phase 5 transition.

Capability set NET_ADMIN/NET_RAW/SYS_ADMIN matches the historical
ospf_injector consumer.py contract; without SYS_ADMIN the FRR daemons
fail cap_set_proc on startup.

NOTE: do not split the image reference across lines — the release-please
extra-files updater matches the entire "image: <ref>" as one token.
*/}}
{{- define "frr-sidecar.container" -}}
{{- if and (and .ospf .ospf.transit_provider) (and .transit (gt (len (default (list) .transit.interfaces)) 0)) -}}
{{- fail (printf "frr-sidecar: workload cannot be both transit provider (ospf.transit_provider=true) and transit consumer (transit.interfaces=%v) at the same time. See frr-sidecar-internal/charts/frr-sidecar/templates/_container.tpl." .transit.interfaces) -}}
{{- end -}}
{{- if .ospf -}}
- name: frr-sidecar
  image: {{ (default "" .image | trim) | default (include "frr-sidecar.defaultImage" . | trim) | quote }}
  imagePullPolicy: IfNotPresent
  env:
    - name: PROFILE
      value: {{ .ospf.profile | default "" | quote }}
    - name: OSPF_ROUTER_ID
      value: {{ .ospf.router_id | default "" | quote }}
    - name: OSPF_INTERFACES
      value: {{ .ospf.interfaces | default (list) | join "," | quote }}
    - name: REDISTRIBUTE
      value: {{ .ospf.redistribute | default (list) | join "," | quote }}
    - name: DEFAULT_ORIGINATE
      value: {{ .ospf.default_originate | default "false" | quote }}
    {{- with .transit }}
    {{- if .interfaces }}
    - name: PBR_TRANSIT_TAG
      value: {{ include "frr-sidecar.transitTag" . | quote }}
    - name: PBR_TRANSIT_INTERFACES
      value: {{ join "," .interfaces | quote }}
    {{- end }}
    {{- end }}
  volumeMounts:
    {{- if .injected }}
    {{- /* MAP-injected volumes: only present when Kyverno MutatingPolicy has added them */}}
    {{- /* mountPath values must match render_frr.py defaults — see image/render_frr.py _DEFAULT_*_MOUNT */}}
    - name: garuda-profile
      mountPath: /etc/garuda/profile
      readOnly: true
    - name: garuda-intent
      mountPath: /etc/garuda/intent
      readOnly: true
    {{- end }}
    - name: frr-source
      mountPath: /etc/frr-source
      readOnly: true
  securityContext:
    capabilities:
      drop: ["ALL"]
      add: ["NET_ADMIN", "NET_RAW", "SYS_ADMIN"]
  readinessProbe:
    httpGet:
      path: /readyz
      port: 9179
    initialDelaySeconds: 5
    periodSeconds: 10
{{- end -}}
{{- end }}
