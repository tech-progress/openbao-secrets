FROM ghcr.io/openbao/openbao:2.7.1@sha256:6d2b93856e3fcf7b18ad855a0b51eaba474dc8b79cf554379ea32034797d2acf AS upstream
FROM python:3.13.12-alpine3.23@sha256:bb1f2fdb1065c85468775c9d680dcd344f6442a2d1181ef7916b60a623f11d40
COPY --from=upstream /usr/bin/bao /usr/bin/bao
COPY --from=upstream /licenses/mozilla.txt /licenses/openbao-MPL-2.0.txt
RUN addgroup -g 10001 bao && adduser -D -H -u 10001 -G bao bao && mkdir /data && chown bao:bao /data
WORKDIR /opt/template
COPY app.py tests.py ./
COPY LICENSE /opt/template/LICENSE
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
EXPOSE 8080
ENTRYPOINT ["python", "/opt/template/app.py"]
