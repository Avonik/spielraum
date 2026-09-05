FROM python:3.12-slim-bookworm AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NUMBA_CACHE_DIR=/data/numba-cache \
    MPLCONFIGDIR=/data/matplotlib

WORKDIR /app
RUN useradd --create-home --uid 1000 spielraum
COPY portfolio-requirements.txt ./
RUN pip install --no-cache-dir --prefer-binary -r portfolio-requirements.txt
COPY spielraum ./spielraum
RUN mkdir -p /data && chown -R spielraum:spielraum /data /app
USER spielraum

EXPOSE 8000
CMD ["uvicorn", "spielraum.api:app", "--host", "0.0.0.0", "--port", "8000"]

FROM api AS worker
USER root
COPY v2/requirements.txt /tmp/v2-requirements.txt
RUN pip install --no-cache-dir --prefer-binary -r /tmp/v2-requirements.txt
COPY --chown=spielraum:spielraum v2 ./v2
USER spielraum
CMD ["python", "-m", "spielraum.scheduler"]
