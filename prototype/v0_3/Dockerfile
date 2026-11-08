FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY server.py video.py archive.py /app/
ENV PYTHONUNBUFFERED=1 DATA_DIR=/data
EXPOSE 8000
CMD ["python", "/app/server.py"]
