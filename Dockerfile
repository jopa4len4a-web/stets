FROM python:3.11-slim

# Устанавливаем Node.js 20
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Node.js-зависимости
COPY package.json .
RUN npm install --production

# Копируем код
COPY . .

# Запускаем Python-бота
CMD ["python", "bot.py"]
