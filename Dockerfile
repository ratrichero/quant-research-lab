FROM python:3.10-slim

# Bắt buộc có dòng này để tránh lỗi debconf
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# 1️⃣ Copy requirements trước
COPY requirements.txt .

# 2️⃣ Install dependencies (layer này sẽ được cache)
RUN pip install --no-cache-dir -r requirements.txt

# 3️⃣ Copy source code sau cùng
COPY . .

CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080"]