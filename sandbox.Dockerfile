FROM python:3.12-slim
RUN useradd --uid 10001 --create-home runner
WORKDIR /workspace
USER 10001:10001
ENV HOME=/home/runner PYTHONDONTWRITEBYTECODE=1
CMD ["/bin/sh"]
