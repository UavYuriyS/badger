FROM alpine:3.16
RUN apk add --no-cache \
        uwsgi-python3 \
        uwsgi-http \
        python3 \
        py3-pip

ENV DB_HOST=localhost
ENV DB_PORT=6379
ENV PORT=5050
ENV API_KEY="seriously.change this"

WORKDIR /usr/src/app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD uwsgi --plugins python3,http --http 0.0.0.0:$PORT --uid uwsgi --protocol uwsgi -p 4 --wsgi wsgi:app