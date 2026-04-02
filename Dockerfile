FROM python:3.12-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

# Fly задаёт PORT; лёгкий HTTP для прокси/health, параллельно polling в том же event loop.
CMD ["python", "fly_entry.py"]
