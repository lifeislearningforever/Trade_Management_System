# Deployment Guide

Deploy CisTrade to production environment.

## Pre-Deployment Checklist

- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Database migrations tested
- [ ] Static files collected
- [ ] Environment variables configured
- [ ] Backup plan ready
- [ ] Rollback plan documented

## Production Environment

### Server Requirements

- **OS**: Linux (RHEL/Ubuntu)
- **Python**: 3.10+
- **Web Server**: Nginx
- **WSGI Server**: Gunicorn
- **Database**: Impala cluster access
- **Memory**: 8GB+ RAM
- **Storage**: 100GB+ SSD

### Network Requirements

- **Impala**: Port 21050 (JDBC), 21000 (shell)
- **HTTP**: Port 80
- **HTTPS**: Port 443
- **SSH**: Port 22

## Deployment Steps

### 1. Prepare Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install python3 python3-pip python3-venv nginx -y
```

### 2. Create Application User

```bash
sudo useradd -m -s /bin/bash cistrade
sudo su - cistrade
```

### 3. Deploy Application

```bash
# Clone repository
git clone https://github.com/yourcompany/cistrade.git
cd cistrade

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install gunicorn
```

### 4. Configure Environment

Create `/home/cistrade/cistrade/.env`:

```env
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=<generate-secure-key>
DJANGO_ALLOWED_HOSTS=cistrade.yourcompany.com,10.x.x.x

IMPALA_HOST=prod-impala-host
IMPALA_PORT=21050
IMPALA_DATABASE=gmp_cis

# Security
CSRF_COOKIE_SECURE=true
SESSION_COOKIE_SECURE=true
```

### 5. Collect Static Files

```bash
python manage.py collectstatic --noinput
```

### 6. Run Migrations

```bash
python manage.py migrate
```

### 7. Test Application

```bash
python manage.py check --deploy
```

### 8. Configure Gunicorn

Create `/etc/systemd/system/cistrade.service`:

```ini
[Unit]
Description=CisTrade Gunicorn daemon
After=network.target

[Service]
User=cistrade
Group=cistrade
WorkingDirectory=/home/cistrade/cistrade
Environment="PATH=/home/cistrade/cistrade/.venv/bin"
ExecStart=/home/cistrade/cistrade/.venv/bin/gunicorn \
    --workers 4 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile /var/log/cistrade/access.log \
    --error-logfile /var/log/cistrade/error.log \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

Start service:

```bash
sudo systemctl daemon-reload
sudo systemctl start cistrade
sudo systemctl enable cistrade
```

### 9. Configure Nginx

Create `/etc/nginx/sites-available/cistrade`:

```nginx
server {
    listen 80;
    server_name cistrade.yourcompany.com;

    client_max_body_size 10M;

    location /static/ {
        alias /home/cistrade/cistrade/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/cistrade /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 10. SSL Configuration (HTTPS)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d cistrade.yourcompany.com
```

## Post-Deployment

### Verify Deployment

1. Access https://cistrade.yourcompany.com
2. Test login
3. Check all modules functional
4. Review logs for errors

### Monitoring Setup

**Log Monitoring**:
```bash
tail -f /var/log/cistrade/error.log
tail -f /var/log/nginx/error.log
```

**Service Status**:
```bash
sudo systemctl status cistrade
sudo systemctl status nginx
```

### Backup Configuration

**Daily Backups**:
- Application code (Git)
- Environment configuration
- Database snapshots

**Backup Script** (`/home/cistrade/backup.sh`):
```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR=/backups/cistrade/$DATE

mkdir -p $BACKUP_DIR
cp /home/cistrade/cistrade/.env $BACKUP_DIR/
# Add database backup commands
```

## Rollback Procedure

If deployment fails:

1. **Stop services**:
```bash
sudo systemctl stop cistrade
```

2. **Restore previous version**:
```bash
cd /home/cistrade/cistrade
git checkout <previous-tag>
```

3. **Rollback migrations** (if needed):
```bash
python manage.py migrate <app> <previous-migration>
```

4. **Restart services**:
```bash
sudo systemctl start cistrade
```

## Scaling

### Horizontal Scaling

Add more Gunicorn workers:

```ini
ExecStart=... --workers 8  # Increase from 4
```

### Load Balancing

Configure Nginx upstream:

```nginx
upstream cistrade_backend {
    server 10.x.x.1:8000;
    server 10.x.x.2:8000;
}

location / {
    proxy_pass http://cistrade_backend;
}
```

## Security Hardening

1. **Firewall**:
```bash
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

2. **Disable DEBUG**:
```env
DJANGO_DEBUG=false
```

3. **Secure SECRET_KEY**:
```python
# Generate secure key
python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

4. **Regular Updates**:
```bash
sudo apt update && sudo apt upgrade -y
pip list --outdated
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u cistrade -n 50 --no-pager

# Check permissions
ls -la /home/cistrade/cistrade
```

### Nginx Errors

```bash
# Test configuration
sudo nginx -t

# Check logs
tail -f /var/log/nginx/error.log
```

### Database Connection Issues

1. Verify Impala host reachable
2. Check firewall rules
3. Test connection manually

## Maintenance

### Update Application

```bash
cd /home/cistrade/cistrade
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart cistrade
```

### Certificate Renewal

Certbot auto-renews. Test with:

```bash
sudo certbot renew --dry-run
```

## Related Documentation

- [Development Guide](development-guide.md)
- [Architecture](architecture.md)
- [Testing](testing.md)
