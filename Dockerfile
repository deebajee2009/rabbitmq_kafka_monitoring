# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY ./requirements/base.txt .
RUN pip install -r base.txt

COPY . .

EXPOSE 8000 8001

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
