FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Copy requirements file to the container
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code to the container
COPY . /app/

# Expose the desired port
EXPOSE 8081

# Run the Streamlit application
CMD ["streamlit", "run", "QA.py", "--server.port", "8081"]
