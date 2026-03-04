# Multi-Instance API Deployment Guide

This guide explains how to run multiple Ada API instances with load balancing for high availability and increased throughput.

## Architecture

```
┌─────────────────┐
│  Client (8000)  │
└────────┬────────┘
         │
    ┌────▼─────┐
    │  Nginx   │  (Load Balancer)
    │ :80 int  │
    └────┬─────┘
         │
    ┌────▼─────────────────┐
    │   api service DNS    │
    │  (Docker resolver)   │
    └─┬──────┬──────┬──────┘
      │      │      │
   ┌──▼──┬───▼──┬───▼──┐
   │ api │ api  │ api  │  (Scaled instances)
   │  1  │  2   │  3   │
   └──┬──┴───┬──┴───┬──┘
      │      │      │
   ┌──▼──────▼──────▼──┐
   │    PostgreSQL     │  (Shared database with connection pooling)
   └──────────┬────────┘
              │
   ┌──────────▼────────┐
   │      Redis        │  (Shared broker)
   └───────────────────┘
```

## Quick Start

### 1. Single API Instance (Default)
```bash
docker-compose up
```
Access API at: http://localhost:8000

### 2. Multiple API Instances (Scaled)
```bash
# Scale to 3 API instances
docker-compose up --scale api=3

# Scale to 5 API instances
docker-compose up --scale api=5
```

Nginx automatically load balances across all instances using least-connections algorithm.

### 3. Verify Load Balancing
```bash
# Check which backend served each request
curl -I http://localhost:8000/health
# Response includes: X-Upstream-Server: <ip>:<port>

# Multiple requests will show different backend IPs
for i in {1..10}; do
  curl -s -I http://localhost:8000/health | grep X-Upstream-Server
done
```

## Configuration

### Load Balancing Algorithm

Edit `docker/nginx.conf` to change the algorithm:

```nginx
upstream api_backend {
    # Options:
    # least_conn - Route to server with fewest active connections (default)
    # ip_hash - Session affinity based on client IP
    # round_robin - Simple rotation (remove least_conn directive)
    least_conn;
    
    server api:80 max_fails=3 fail_timeout=30s;
}
```

### Database Connection Pooling

Configure per-instance connection limits via environment variables:

```yaml
# docker-compose.yml or .env
DB_POOL_SIZE=5          # Base connections per API instance
DB_MAX_OVERFLOW=10      # Extra connections during spikes
DB_POOL_TIMEOUT=30      # Seconds to wait for connection
DB_POOL_RECYCLE=3600    # Recycle connections after 1 hour
```

**Example calculation:**
- 3 API instances × (5 base + 10 overflow) = 45 max connections
- PostgreSQL default: `max_connections=100`
- Leave headroom for workers and manual connections

### Health Checks

Each API instance has a health check:
```bash
# Check individual instance (requires docker exec)
docker exec ada-coding-agent-api-1 curl http://localhost:80/health

# Check via nginx load balancer
curl http://localhost:8000/health
```

## Scaling Strategies

### Development/Testing
```bash
# 2-3 instances for testing load balancing
docker-compose up --scale api=2 --scale worker=2
```

### Production (Docker Compose)
```bash
# 4-5 API instances + multiple workers
docker-compose up --scale api=4 --scale worker=8 -d
```

### Production (Kubernetes)
See `k8s/deployment.yaml` for Kubernetes manifests with:
- Horizontal Pod Autoscaler (HPA)
- Resource limits
- Liveness/readiness probes

## Performance Tuning

### 1. Nginx Worker Processes
Edit `docker/nginx.conf`:
```nginx
# At the top of file (optional)
worker_processes auto;  # Use all CPU cores
worker_connections 1024;
```

### 2. API Worker Threads
FastAPI runs on Uvicorn. To increase concurrency per instance:

Edit `docker/Dockerfile` or override command:
```yaml
api:
  command: ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "80", "--workers", "4"]
```

**Note:** With async endpoints, you may not need multiple workers. Each worker handles hundreds of concurrent requests.

### 3. Database Connection Limits
Increase PostgreSQL max connections:
```yaml
db:
  environment:
    - POSTGRES_MAX_CONNECTIONS=200
  command: postgres -c max_connections=200
```

### 4. Redis Connection Pooling
Redis handles this automatically. Monitor with:
```bash
docker exec ada-coding-agent-redis-1 redis-cli INFO clients
```

## Monitoring

### Nginx Status
```bash
# Access nginx status (from inside nginx container)
docker exec ada-coding-agent-nginx-1 wget -qO- http://localhost/nginx_status
```

### API Instance Metrics
Monitor per-instance:
- Request count: Check nginx access logs
- Active connections: `netstat` in container
- Database pool: Add metrics endpoint to FastAPI

### Example: Monitor Scaling in Real-Time
```bash
# Terminal 1: Watch docker containers
watch docker-compose ps

# Terminal 2: Generate load
ab -n 1000 -c 50 http://localhost:8000/health

# Terminal 3: Monitor nginx logs
docker-compose logs -f nginx
```

## Troubleshooting

### Issue: Some instances not receiving requests
**Cause:** Nginx DNS caching or instance not healthy

**Solution:**
```bash
# Check health of all API instances
docker-compose ps api

# Restart nginx to refresh DNS
docker-compose restart nginx
```

### Issue: Connection pool exhausted
**Symptoms:** `sqlalchemy.exc.TimeoutError: QueuePool limit exceeded`

**Solution:**
```bash
# Increase pool size or reduce API instances
export DB_POOL_SIZE=10
export DB_MAX_OVERFLOW=20
docker-compose up --scale api=3
```

### Issue: Uneven load distribution
**Cause:** Long-running requests block instances

**Solution:**
- Use `least_conn` algorithm (default)
- Ensure async endpoints don't block
- Add request timeouts in nginx

## Best Practices

1. **Start Small, Scale Up**
   - Begin with 2 instances to verify load balancing
   - Monitor database connection usage
   - Scale gradually based on metrics

2. **Async All The Way**
   - Use `AsyncLLMClient` for non-blocking LLM calls
   - Async API endpoints (already implemented)
   - This maximizes throughput per instance

3. **Database Connection Math**
   ```
   Total Connections = (API instances × (POOL_SIZE + MAX_OVERFLOW)) + (Worker instances × 2)
   
   Keep under 70% of PostgreSQL max_connections
   ```

4. **Health Check Validity**
   - Current health check is basic (returns 200)
   - Consider adding database ping
   - Add Redis connectivity check

5. **Graceful Shutdown**
   ```bash
   # Stop gracefully (waits for in-flight requests)
   docker-compose down --timeout 60
   ```

## Next Steps

- [ ] Add Prometheus metrics for monitoring
- [ ] Implement sticky sessions if needed (ip_hash)
- [ ] Set up Kubernetes deployment for cloud auto-scaling
- [ ] Add circuit breaker for failing backends
- [ ] Configure SSL/TLS termination at nginx

## Related Files

- `docker-compose.yml` - Service orchestration with scaling support
- `docker/nginx.conf` - Load balancer configuration
- `api/database.py` - Connection pooling settings
- `api/main.py` - FastAPI async endpoints
