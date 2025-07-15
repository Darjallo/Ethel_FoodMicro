FROM python:3.11-slim

WORKDIR /app/flow_manager

COPY ethelflow/ .

COPY agent_pool .

EXPOSE 8080
CMD ["python", "-m", "ethelflow"]
