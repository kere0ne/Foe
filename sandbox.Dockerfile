FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pytest ruff \
    && useradd --uid 10001 --create-home runner
WORKDIR /workspace
USER 10001:10001
ENV HOME=/home/runner PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS="-p no:cacheprovider"
CMD ["/bin/sh"]
