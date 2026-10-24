# Build context is the repository root:  docker compose build
FROM maven:3.9-eclipse-temurin-17 AS dss
WORKDIR /build
COPY dss/ .
RUN mvn -q -DskipTests package

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-fra \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-hosny-amiri fonts-dejavu-core \
      openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ api/
COPY scripts/ scripts/
COPY templates/ templates/
COPY --from=dss /build/target/vaultiq-dss.jar dss/target/vaultiq-dss.jar
RUN useradd -m vaultiq && mkdir -p vault/signed certs && chown -R vaultiq /app
USER vaultiq
EXPOSE 8000
CMD ["sh", "-c", "python scripts/gen_certs.py && uvicorn api.main:app --host 0.0.0.0 --port 8000"]
