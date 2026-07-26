FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/app/data/uploads
EXPOSE 5000
CMD ["sh", "-c", "python -c 'from app.models import init_db; init_db()' && gunicorn -w 2 -b 0.0.0.0:5000 app.main:app"]
