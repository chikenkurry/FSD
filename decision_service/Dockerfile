FROM python:3.12-slim

WORKDIR /app
COPY decision_service /app/decision_service
RUN mkdir -p /data && chown nobody:nogroup /data
USER nobody
EXPOSE 8000

CMD ["python", "-m", "decision_service.service"]
