FROM python:3.10-slim

WORKDIR /app

# System deps for rasterio/GDAL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgdal-dev gdal-bin libgeos-dev build-essential fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501 8000
