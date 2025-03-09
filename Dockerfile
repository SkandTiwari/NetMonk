FROM python:3.9-slim

WORKDIR /app

RUN apt-get update

COPY requirements.txt .

RUN pip3 install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "dnac_demo.py"]
