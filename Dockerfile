FROM python:3.10-slim

# System setup
RUN apt-get update && apt-get install -y curl procps zstd && rm -rf /var/lib/apt/lists/*

# Install Ollama via official script
RUN curl -fsSL https://ollama.com/install.sh | sh

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Environment Variables
ENV PORT=8080
ENV OLLAMA_HOST=127.0.0.1:11434
ENV PYTHONUNBUFFERED=1

# Execution Script: Starts Ollama, pulls Llama 3.2 (3B - Optimal for CPU), starts App
RUN echo '#!/bin/bash\nollama serve & sleep 10 && ollama pull llama3.2 && python app.py' > /app/run.sh && \
    chmod +x /app/run.sh

EXPOSE 8080
CMD ["/app/run.sh"]
