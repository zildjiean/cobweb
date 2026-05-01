FROM zaproxy/zap-stable:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3-pip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY workers/zap-runner/requirements.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt
COPY workers/zap-runner /app
USER zap
ENTRYPOINT ["python3", "-m", "runner"]
