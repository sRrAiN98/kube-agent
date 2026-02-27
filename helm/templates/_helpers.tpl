{{/*
Expand the name of the chart.
*/}}
{{- define "blueprint.name" -}}
{{- default .name .spec.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "blueprint.fullname" -}}
{{- if .spec.fullnameOverride }}
{{- .spec.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .name .spec.nameOverride }}
{{- if contains $name .root.Release.Name }}
{{- .root.Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .root.Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "blueprint.chart" -}}
{{- printf "%s-%s" .root.Chart.Name .root.Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "blueprint.labels" -}}
helm.sh/chart: {{ include "blueprint.chart" . }}
{{ include "blueprint.selectorLabels" . }}
{{- if .root.Chart.AppVersion }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "blueprint.selectorLabels" -}}
app.kubernetes.io/name: {{ include "blueprint.name" . }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "blueprint.serviceAccountName" -}}
{{- if .spec.serviceAccount.create }}
{{- default (include "blueprint.fullname" .) .spec.serviceAccount.name }}
{{- else }}
{{- default "default" .spec.serviceAccount.name }}
{{- end }}
{{- end }}