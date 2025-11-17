# file: Dockerfile

# Use a slim Python base image
FROM python:3.12-slim

# Prevent Python from writing .pyc files and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set work directory in the container
WORKDIR /app

# System deps (optional, but handy if you add compiled packages later)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Expose the port Uvicorn will listen on
EXPOSE 9000

# Default command: run the FastAPI app
# NOTE: src.scryfall_ui.web_app defines `app = FastAPI(...)` :contentReference[oaicite:3]{index=3}
CMD ["uvicorn", "src.scryfall_ui.web_app:app", "--host", "0.0.0.0", "--port", "9000"]
