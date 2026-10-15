# Упаковка уже СОБРАННОГО артефакта (wheel из dist/) в контейнер.
FROM python:3.12-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv
COPY dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm -f /tmp/*.whl

RUN useradd --system --no-create-home appuser
USER appuser

# Порт берётся из переменной PORT (на Render задаётся автоматически), локально - 8000
ENV PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:%s/health' % os.environ.get('PORT','8000'), timeout=2)"

CMD ["sh", "-c", "uvicorn sysapp.main:app --host 0.0.0.0 --port ${PORT}"]
