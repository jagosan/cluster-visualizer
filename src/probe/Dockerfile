# clustervis-probe: unprivileged TCP RTT probe daemon (TASK-CV-802, SPEC-07 §4.1)
# Zero third-party dependencies — stdlib only.
FROM python:3.12-alpine

# Non-privileged runtime user (no shell, no home writes needed).
RUN addgroup -g 65532 -S probe && adduser -u 65532 -S -G probe -D probe

# tini-less reaping: python handles SIGTERM/SIGINT directly in main().
WORKDIR /app
COPY src/probe/main.py /app/main.py

# The app binds an unprivileged port (9102) and needs no capabilities.
USER 65532:65532
EXPOSE 9102/tcp

ENV PROBE_PORT=9102
ENTRYPOINT ["python", "-u", "/app/main.py"]
