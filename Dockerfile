FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y \
    libpoppler-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY extract_sections.py .
CMD ["python", "extract_sections.py", "/app/pdfs", "PhD Researcher", "Prepare a literature review", "/app/output.json"]
