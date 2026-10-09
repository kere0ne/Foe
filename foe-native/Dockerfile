FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY foe_native ./foe_native
ENV FOE_CHECKPOINT=/models/latest.pt
EXPOSE 8090
CMD ["python", "-m", "foe_native.serve", "--host", "0.0.0.0", "--port", "8090"]
