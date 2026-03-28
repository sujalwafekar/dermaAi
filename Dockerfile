FROM python:3.11-slim

# Install system dependencies + Node.js for React build
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    git \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Set up a non-root user for Hugging Face Spaces compatibility
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Copy and install Python dependencies first (layer cache)
COPY --chown=user:user backend/requirements.txt ./backend/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r backend/requirements.txt gunicorn

# Copy all project files
COPY --chown=user:user . .

# Build the React frontend
WORKDIR $HOME/app/Dermiyaaiii
RUN npm install --legacy-peer-deps && npm run build

# Set working directory to backend
WORKDIR $HOME/app/backend

ENV PORT=7860
EXPOSE 7860

CMD ["gunicorn", "app:app", "--workers", "1", "--threads", "2", "--timeout", "120", "--bind", "0.0.0.0:7860"]
