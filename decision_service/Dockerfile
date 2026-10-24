FROM python:3.12-slim

WORKDIR /app
COPY decision_service/requirements.txt /app/decision_service/requirements.txt
RUN pip install --no-cache-dir -r /app/decision_service/requirements.txt
COPY decision_service /app/decision_service
RUN mkdir -p /data && chown nobody:nogroup /data
USER nobody
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/health/ready', timeout=2)"

CMD ["python", "-m", "decision_service.service"]
