{{/*
frr-sidecar default container image.

The tag on the line below is the frr-sidecar chart version and is bumped by
release-please (extra-files generic updater, keyed off the inline annotation
comment). Do not edit the tag by hand, and DO NOT split the image line: the
semver tag and its trailing annotation comment MUST remain on one line, or the
updater will silently stop bumping the tag.
*/}}
{{- define "frr-sidecar.defaultImage" -}}
ghcr.io/garuda-tunnel/garuda-frr-sidecar:0.3.0 {{/* x-release-please-version */}}
{{- end -}}
