{{/* master 3 + replica 3. Job의 클러스터 묶기 명령도 이 수를 기준으로 동작한다. */}}
{{- define "redis.nodeCount" -}}6{{- end -}}

{{- define "redis.selectorLabels" -}}
app.kubernetes.io/name: redis
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* 앱 접속과 Job·재합류 스크립트가 같은 Secret key를 읽는다. */}}
{{- define "redis.passwordEnv" -}}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ required "platform.secretName is required" .Values.platform.secretName | quote }}
      key: {{ required "platform.keys.redisPassword is required" .Values.platform.keys.redisPassword | quote }}
{{- end -}}
