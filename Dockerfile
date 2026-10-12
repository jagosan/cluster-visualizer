FROM python:3.11-slim
WORKDIR /app
COPY src /app/src
COPY dist /app/dist
ENV PYTHONPATH=/app
ENV PORT=8080
ENV CLUSTERVIS_DIST_DIR=/app/dist
EXPOSE 8080
CMD ["python3", "-m", "src.operator.gateway", "--dist-dir", "/app/dist"]
