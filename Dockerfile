FROM python:3.8

# docker build --ssh default=${HOME}/.ssh/id_ed25519 -t metrized-proj-tools .

RUN mkdir -m 700 /root/.ssh; \
    touch -m 600 /root/.ssh/known_hosts; \
    ssh-keyscan github.com > /root/.ssh/known_hosts

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libgl1 libgl1-mesa-glx \
    libglib2.0-0 

WORKDIR /app

# Dependencies
RUN python -m pip install -U pip
COPY requirements/base.txt requirements.txt
RUN --mount=type=ssh pip install -r requirements.txt

# Server application
COPY ./src ./src 
COPY pyproject.toml pyproject.toml
RUN python -m pip install -e .

CMD ["uvicorn", "metrized_ml_server.server:app", "--host", "0.0.0.0", "--port", "8000"]

