# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY query_clothes_service.py .

# Expose the port the app runs on
EXPOSE 5003

# Set environment variable to ensure Python output is unbuffered
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["python", "query_clothes_service.py"]

