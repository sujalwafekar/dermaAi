FROM python:3.11-slim

# Install system dependencies (OpenCV requires libgl1)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up a non-root user for Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy requirement files first for layer caching
COPY --chown=user:user backend/requirements.txt ./backend/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend/requirements.txt gunicorn

# Copy only what's needed — backend + plain HTML frontend (NOT the React app)
COPY --chown=user:user backend/ ./backend/
COPY --chown=user:user frontend/ ./frontend/

# Set working directory to backend
WORKDIR $HOME/app/backend

ENV PORT=7860
EXPOSE 7860

CMD ["gunicorn", "app:app", "--workers", "1", "--threads", "2", "--timeout", "120", "--bind", "0.0.0.0:7860"]
