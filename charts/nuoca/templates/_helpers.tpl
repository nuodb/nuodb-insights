{{/* vim: set filetype=mustache: */}}
{{/*
Expand the name of the chart.
*/}}
{{- define "nuoca.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "nuoca.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "nuoca.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels
*/}}
{{- define "nuoca.labels" -}}
helm.sh/chart: {{ include "nuoca.chart" . }}
{{ include "nuoca.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{/*
Selector labels
*/}}
{{- define "nuoca.selectorLabels" -}}
app.kubernetes.io/name: {{ include "nuoca.name" . }}
app.kubernetes.io/instance: {{ quote .Release.Name }}
{{- end -}}

{{/*
Create the name of the service account to use
*/}}
{{- define "nuoca.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
    {{ default (include "nuoca.fullname" .) .Values.serviceAccount.name }}
{{- else -}}
    {{ default "default" .Values.serviceAccount.name }}
{{- end -}}
{{- end -}}

{{/*
NuoAdmin URL
*/}}
{{- define "nuoca.nuodb_api_server" -}}
{{- $hostname := default .Values.nuoadmin.host "nuodb" -}}
{{- $port     := default .Values.nuoadmin.port 8888 -}}
{{- if .Values.nuoadmin.tls.enabled -}}
{{-   printf "https://%s:%d" $hostname $port -}}
{{- else -}}
{{-   printf "http://%s:%d" $hostname $port -}}
{{- end -}}
{{- end -}}


{{- define "nuoca.influxdb_url" -}}
{{- $hostname := default (printf "%s-influxdb" .Release.Name) .Values.influxdb.host -}}
{{- $port     := default 8086 .Values.influxdb.port -}}
{{- $db       := default "nuodb" .Values.influxdb.dbname -}}
{{- printf "http://%s:%d/write?db=%s" $hostname $port $db -}}
{{- end -}}
