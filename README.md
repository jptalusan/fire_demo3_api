# Fire Demo3 API

A FastAPI application that serves data files.

## Installation

Install dependencies:

```bash
pip install -e .
```

## Running

Run the application:

```bash
python src/app.py
```

Or with uvicorn:

```bash
uvicorn src.app:app --reload

# With debug
uv run uvicorn src.app:app --reload --log-level debug --host 0.0.0.0 --port 8000
```

## Nginx
```bash
# Create certificates
sudo yum install libcurl4-openssl-dev nginx
sudo mkdir -p /etc/ssl/private
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout /etc/ssl/private/dash-selfsigned.key -out /etc/ssl/certs/dash-selfsigned.crt -subj "/C=US/ST=Test/L=Test/O=Test/OU=Test/CN=localhost"

# setup nginx
sudo systemctl enable nginx
sudo cp .nginx/dash_app.conf /etc/nginx/conf.d/dash_app.conf
sudo nginx -t && sudo systemctl restart nginx
```
