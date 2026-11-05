FROM nginx:alpine

LABEL org.opencontainers.image.source="https://github.com/mrimoczi/pedasszisztens"

# Serve text with an explicit UTF-8 charset
RUN echo 'charset utf-8; charset_types text/html text/css text/plain application/javascript;' > /etc/nginx/conf.d/charset.conf

COPY src/index.html /usr/share/nginx/html/index.html
COPY src/hangok/timings.js src/hangok/*.mp3 /usr/share/nginx/html/hangok/

EXPOSE 80
