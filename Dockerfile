FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY power_notifier ./power_notifier
# .env і data/ (з файлом сесії) монтуються ззовні, див. README
VOLUME ["/app/data"]
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "power_notifier", "run"]
