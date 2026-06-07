{{/*
Render the `frr-sidecar-init` init container.

Usage (inside spec.template.spec.initContainers, with 8-space indent):
    {{- $init := include "frr-sidecar.initContainer" (dict
          "image" .Values.images.frr
          "ospf"  .Values.ospf
        ) -}}
    {{- if $init }}
    initContainers:
      {{- $init | nindent 8 }}
    {{- end }}

The template is a no-op (returns empty string) for the compose-era
transit provider contract — the provider does NOT need a pre-FRR
init step. Callers wrap the include in `{{ if $init }}...{{ end }}`
so the `initContainers:` field is omitted entirely.

Retained as a named template for backward compatibility with consumer
deployment.yaml callsites; future provider mechanisms that DO need an
init step can re-introduce content here without churning callers.
*/}}
{{- define "frr-sidecar.initContainer" -}}
{{- /* no-op */ -}}
{{- end -}}
