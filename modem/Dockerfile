FROM python:3.12-slim
RUN pip install --no-cache-dir numpy==2.1.3
WORKDIR /app
COPY minitel_modem /app/minitel_modem
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "minitel_modem.server"]
