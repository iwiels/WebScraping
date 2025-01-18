FROM python:3.10-slim

# Instalar Chrome y dependencias necesarias
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Configurar variables de entorno para Chrome
ENV CHROME_BIN=/usr/bin/google-chrome
ENV CHROME_PATH=/usr/bin/google-chrome

# Directorio de trabajo
WORKDIR /app

# Copiar requirements.txt
COPY requirements.txt .

# Instalar dependencias sin actualizar pip
RUN pip install -r requirements.txt

# Copiar el resto del código
COPY . .

# Variables de entorno
ENV PORT=10000
ENV PYTHONPATH=/app

# Comando para ejecutar la aplicación con timeout aumentado
CMD gunicorn --bind 0.0.0.0:$PORT --timeout 300 --workers 3 app:app
