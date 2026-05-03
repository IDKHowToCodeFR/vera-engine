FROM python:3.10-slim

# System setup
RUN apt-get update && apt-get install -y curl procps && rm -rf /var/lib/apt/lists/*

# Install Ollama Binary
RUN curl -L https://ollama.com/download/ollama-linux-amd64 -o /usr/bin/ollama && \
    chmod +x /usr/bin/ollama

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment Variables
ENV PORT=8086
ENV OLLAMA_HOST=127.0.0.1:11434
ENV PYTHONUNBUFFERED=1

# Execution Script: Starts Ollama, pulls Phi, starts App
RUN echo '#!/bin/bash\nollama serve & sleep 5 && ollama pull phi3.5 && python app.py' > /app/run.sh && \
    chmod +x /app/run.sh

EXPOSE 8086
CMD ["/app/run.sh"]
