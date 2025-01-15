# Use the official Python image as the base image
FROM python:3.9-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Set the working directory to the root of the container's filesystem
WORKDIR /

# Copy the requirements file and install dependencies
COPY requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy the rest of the application code to the root directory
COPY . .

# Expose the port your application runs on (if applicable)
# EXPOSE 8000

# Set the command to run your application
CMD ["python", "main.py"]
