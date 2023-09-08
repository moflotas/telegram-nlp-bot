FROM python:3.10-bullseye

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "-u", "./main.py" ]