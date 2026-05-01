FROM projectdiscovery/nuclei:latest AS nuclei

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 1001 -m runner
COPY --from=nuclei /usr/local/bin/nuclei /usr/local/bin/nuclei
COPY workers/nuclei-runner/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY workers/nuclei-runner /app
USER 1001
ENTRYPOINT ["python", "-m", "runner"]
