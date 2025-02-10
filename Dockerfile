# Use the official Python image with version 3.9
FROM python:3.9-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . .

# Install Python dependencies from the requirements.txt file
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000 (the port Flask runs on)
EXPOSE 5000

# Command to run the Flask application
CMD ["python", "python_flask.py"]
