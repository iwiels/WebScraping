FROM python:3.9-slim

# Instalar Microsoft Edge y sus dependencias
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    wget \
    && curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > microsoft.gpg \
    && install -o root -g root -m 644 microsoft.gpg /etc/apt/trusted.gpg.d/ \
    && echo "deb [arch=amd64] https://packages.microsoft.com/repos/edge stable main" > /etc/apt/sources.list.d/microsoft-edge.list \
    && apt-get update \
    && apt-get install -y microsoft-edge-stable \
    && rm -rf /var/lib/apt/lists/*

# Directorio de trabajo
WORKDIR /app

# Copiar requirements.txt
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY . .

# Variables de entorno
ENV PORT=10000
ENV PYTHONPATH=/app

# Comando para ejecutar la aplicación
CMD gunicorn --bind 0.0.0.0:$PORT app:app
