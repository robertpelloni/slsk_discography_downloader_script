FROM rust:1.75-slim-bookworm AS rust-builder
WORKDIR /app

# Install dependencies needed for python and rust compilation
RUN apt-get update && apt-get install -y python3-dev python3-pip python3-venv curl build-essential

# Create a virtual environment and install maturin
RUN python3 -m venv /venv
ENV PATH="/venv/bin:$PATH"
RUN pip install maturin

# Copy the rust source code
COPY discography_webapp/rust_bridge/ /app/rust_bridge/

# Build the Rust wheel
WORKDIR /app/rust_bridge
RUN maturin build --release --out /wheels

FROM python:3.12-slim-bookworm
WORKDIR /app

# Copy the built wheel from the builder stage
COPY --from=rust-builder /wheels /wheels

# Copy application files
COPY discography_webapp/ /app/discography_webapp/
COPY VERSION.md /app/

# Install dependencies and the built Rust wheel
RUN pip install --no-cache-dir -r /app/discography_webapp/requirements.txt \
    && pip install --no-cache-dir /wheels/*.whl

# Expose the application port
EXPOSE 8000

# Run the application
CMD ["python", "/app/discography_webapp/main.py"]
