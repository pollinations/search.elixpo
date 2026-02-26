# Production Deployment Guide for lixSearch

This guide covers deploying lixSearch using the production Docker Compose configuration with Nginx as the single public endpoint.

## Quick Start

### 1. Prepare Environment

```bash
cd docker_setup/

# Copy and customize environment variables
cp .env.prod .env
nano .env  # Edit with your deployment settings

# Create SSL directory (for HTTPS later)
mkdir -p ssl/
```

### 2. Single-Container Deployment (Development → Production)

```bash
# Start all services (redis, chroma, nginx, lixsearch-app with 10 workers)
docker-compose -f docker-compose.prod.yml up -d

# Verify services are healthy
docker-compose -f docker-compose.prod.yml ps

# Check logs
docker-compose -f docker-compose.prod.yml logs -f nginx
docker-compose -f docker-compose.prod.yml logs -f lixsearch-app
```

**Access Points:**
- API: `http://localhost:80` (or port 443 if HTTPS enabled)
- Health: `http://localhost/api/health`

### 3. Multi-Container Deployment (Horizontal Scaling)

When you need to scale from 1 to 3+ containers:

```bash
# Start with 3 containers (3 × 10 workers = 30 parallel processors)
docker-compose -f docker-compose.prod.yml up -d --scale lixsearch-app=3

# Verify all 3 containers started
docker-compose -f docker-compose.prod.yml ps
# Should show:
# lixsearch-nginx                  RUNNING
# lixsearch-redis                  RUNNING
# lixsearch-chroma                 RUNNING
# lixsearch-app (3 instances)      RUNNING

# Scale to 5 containers
docker-compose -f docker-compose.prod.yml up -d --scale lixsearch-app=5

# Scale back down
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d --scale lixsearch-app=2
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                   Public Internet                     │
│               (Port 80/443 only)                      │
└───────────────────────┬─────────────────────────────┘
                        │
                   ┌────▼─────┐
                   │  Nginx    │
                   │ Reverse   │
                   │ Proxy &   │
                   │ Load      │
                   │ Balancer  │
                   └────┬─────┘
                        │
        ┌──────────────┬─┴─────────────┬──────────────┐
        │              │               │              │
   ┌────▼───┐  ┌──────▼──┐  ┌────────▼──┐  ┌───────▼──┐
   │ app:1  │  │ app:2   │  │ app:3     │  │ app:...  │
   │ (10    │  │ (10     │  │ (10       │  │ (10      │
   │workers)│  │workers) │  │workers)   │  │workers)  │
   └────┬───┘  └────┬────┘  └─────┬────┘  └───┬──────┘
        │           │             │           │
        └───────────┼─────────────┼───────────┘
                    │ (shared)    │ (shared)
              ┌─────▼───┐    ┌────▼─────┐
              │  Redis  │    │  Chroma  │
              │ (Cache) │    │(Embeddings)
              └─────────┘    └──────────┘

Scaling: Just add more 'app' containers - Nginx auto-routes via Docker DNS
```

## Monitoring & Debugging

### Health Checks

```bash
# Check all services are healthy
curl http://localhost/api/health
# Response: {"status": "ok"}

# Individual service health
docker-compose -f docker-compose.prod.yml ps

# Redis health
docker-compose -f docker-compose.prod.yml exec redis redis-cli ping
# Response: PONG

# Chroma health
curl http://localhost:8001/api/version  # Assuming app is on port 8000+1 internally
```

### Logs

```bash
# Nginx access & error logs
docker-compose -f docker-compose.prod.yml logs -f nginx

# Application logs (all containers)
docker-compose -f docker-compose.prod.yml logs -f lixsearch-app

# Follow specific container
docker-compose -f docker-compose.prod.yml logs -f lixsearch-app-1  # first container
docker-compose -f docker-compose.prod.yml logs -f lixsearch-app-2  # second container

# Redis logs
docker-compose -f docker-compose.prod.yml logs -f redis

# Chroma logs
docker-compose -f docker-compose.prod.yml logs -f chroma-server
```

### performance Monitoring

```bash
# CPU/Memory per container
docker stats

# Network traffic
docker-compose -f docker-compose.prod.yml exec nginx \
  tail -f /var/log/nginx/access.log | jq .

# Redis memory usage
docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory
```

## SSL/HTTPS Setup

### 1. Obtain Certificates

```bash
# Option A: Use Let's Encrypt (recommended for production)
sudo certbot certonly --standalone -d yourdomain.com

# Copy certificates
sudo cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem docker_setup/ssl/cert.pem
sudo cp /etc/letsencrypt/live/yourdomain.com/privkey.pem docker_setup/ssl/key.pem
sudo chown $USER:$USER docker_setup/ssl/*.pem

# Option B: Self-signed certificate (development only)
openssl req -x509 -newkey rsa:4096 -keyout docker_setup/ssl/key.pem \
  -out docker_setup/ssl/cert.pem -days 365 -nodes
```

### 2. Enable HTTPS in nginx.conf

Uncomment/update this section in nginx.conf:

```nginx
server {
  listen 443 ssl http2;
  listen [::]:443 ssl http2;
  server_name yourdomain.com;

  ssl_certificate /etc/nginx/ssl/cert.pem;
  ssl_certificate_key /etc/nginx/ssl/key.pem;
  
  # ... rest of configuration
}

# Redirect HTTP to HTTPS
server {
  listen 80;
  listen [::]:80;
  server_name yourdomain.com;
  return 301 https://$server_name$request_uri;
}
```

### 3. Restart Nginx

```bash
docker-compose -f docker-compose.prod.yml restart nginx
```

## API Usage Examples

### Search Endpoint (Required: session_id parameter)

```bash
# Search query with streaming
curl -X GET \
  "http://localhost/api/search?session_id=user-123&query=What is AI?&stream=true"

# POST request
curl -X POST http://localhost/api/search \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "user-123",
    "query": "What is AI?",
    "stream": true
  }'
```

### Chat Endpoints

```bash
# Start new chat (creates session_id if not provided)
curl -X POST http://localhost/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "session_id": "user-123"}'

# Continue session chat
curl -X POST http://localhost/api/session/user-123/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What was I asking about?"}'

# Get session info and stats
curl http://localhost/api/session/user-123/info
```

## Performance Tuning

### Nginx Rate Limiting

Edit `.env` to adjust:
```bash
RATE_LIMIT_GENERAL=100    # 100 req/sec per IP
RATE_LIMIT_SEARCH=50      # 50 req/sec for /api/search
RATE_LIMIT_CHAT=30        # 30 req/sec for /api/chat
```

These are configured in nginx.conf at zones: `general`, `search`, `chat`

### Redis Memory

Edit `docker-compose.prod.yml` redis service:
```yaml
command: redis-server --appendonly yes --maxmemory 4gb --maxmemory-policy allkeys-lru
```

Current: 2GB, change to 4GB or more for larger deployments

### Connection Pooling

Edit `.env`:
```bash
REDIS_POOL_SIZE=50           # Increase for >5 containers
SEMANTIC_CACHE_REDIS_DB=0    # Stays at DB 0
```

### Worker Count Per Container

Edit `.env`:
```bash
WORKER_COUNT=10  # Change to 16 or 20 for high-traffic containers
```

## Troubleshooting

### Nginx can't connect to backend
1. Check app container is running: `docker-compose -f docker-compose.prod.yml ps`
2. Verify network: `docker network ls`
3. Test connectivity: `docker-compose -f docker-compose.prod.yml exec nginx nslookup lixsearch-app`

### Sessions not isolated
1. Verify sessionID in request: `curl http://localhost/api/search?session_id=test123&query=test`
2. Check Redis DBs: `docker-compose -f docker-compose.prod.yml exec redis redis-cli`
   - `SELECT 0; KEYS *` (session query cache)
   - `SELECT 1; KEYS *` (URL embeddings)
   - `SELECT 2; KEYS *` (session context)

### High memory usage
1. Check Redis: `docker-compose -f docker-compose.prod.yml exec redis redis-cli INFO memory`
2. Check Chroma: `docker docker stats | grep chroma`
3. Review cache TTLs in `.env`

### Slow searches
1. Check Nginx upstreams: `docker-compose -f docker-compose.prod.yml logs nginx | grep upstream`
2. Monitor Chroma: `docker docker logs lixsearch-chroma | tail -100`
3. Increase workers: Edit `.env` WORKER_COUNT and restart

## Production Checklist

- [ ] Environment variables configured in `.env`
- [ ] SSL certificates in place (if using HTTPS)
- [ ] Redis memory limits set appropriately (--maxmemory)
- [ ] Nginx rate limiting configured per your traffic
- [ ] Data backups configured for Redis (AOF enabled in compose)
- [ ] Monitoring/alerting setup (check Nginx and app logs)
- [ ] Load tested: `docker-compose up --scale lixsearch-app=3`
- [ ] Tested sessionID isolation across containers
- [ ] Verified shared Redis/Chroma access from all containers

## Upgrade Path: Single → Multi-Container

```bash
# Current: single container
docker-compose -f docker-compose.prod.yml ps

# Scale to 3 (non-breaking change)
docker-compose -f docker-compose.prod.yml up -d --scale lixsearch-app=3

# All existing sessions continue to work!
# Nginx auto-distributes new requests across 3 containers
# Redis is already shared, no data loss
# Chroma embeddings already shared

# Scale to 5 if needed
docker-compose -f docker-compose.prod.yml up -d --scale lixsearch-app=5

# Scale back down
docker-compose -f docker-compose.prod.yml down
```

## Clean Up

```bash
# Stop all services (keeps data)
docker-compose -f docker-compose.prod.yml down

# Stop and remove all data
docker-compose -f docker-compose.prod.yml down -v

# Remove unused volumes
docker volume prune

# Remove unused images
docker image prune
```

## File Structure

```
docker_setup/
├── docker-compose.prod.yml     # Production configuration
├── docker-compose.yml          # Legacy single-container config
├── .env.prod                   # Template for env variables
├── .env                        # Actual env (create from .env.prod)
├── nginx.conf                  # Nginx load balancer config
├── Dockerfile                  # App image definition
├── entrypoint.sh               # Container startup script
├── DEPLOYMENT_GUIDE.md         # This file
└── ssl/                        # SSL certificates (if HTTPS)
    ├── cert.pem                # Server certificate
    └── key.pem                 # Private key
```

## Next Steps

1. **Configure environment**: Edit `.env` with your settings
2. **Deploy**: `docker-compose -f docker-compose.prod.yml up -d`
3. **Verify**: `curl http://localhost/api/health`
4. **Monitor**: `docker-compose -f docker-compose.prod.yml logs -f`
5. **Scale** (when needed): `--scale lixsearch-app=3`
6. **Enable HTTPS** (production): Copy SSL certs and update nginx.conf

## Support & Documentation

- Scaling architecture: See [PARALLEL_WORKERS_ARCHITECTURE.md](../DOCS/PARALLEL_WORKERS_ARCHITECTURE.md)
- Caching strategy: See [CACHING_EMBEDDINGS_ARCHITECTURE.md](../DOCS/CACHING_EMBEDDINGS_ARCHITECTURE.md)
- Full system architecture: See [FULL_ARCHITECTURE.md](../DOCS/FULL_ARCHITECTURE.md)
