# Docker Deployment Guide

This guide covers deploying the Computer Use Session Backend using a unified Docker container that includes both the FastAPI backend and VNC environment.

## Quick Start

### Prerequisites

- Docker 20.10+ 
- Docker Compose 2.0+
- Git
- At least 4GB RAM available for containers

### Development Setup

1. **Clone and setup environment**:
   ```bash
   git clone <repository-url>
   cd comp_use_agent
   cp .env.example .env  # Create and configure your environment variables
   ```

2. **Set required environment variables**:
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   ```

3. **Start development environment**:
   ```bash
   # Quick setup with automated script
   ./docker-setup.sh
   
   # Or manual setup with hot reloading
   docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
   ```

4. **Access services**:
   - FastAPI Backend: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - VNC Interface: http://localhost:8080
   - Database Viewer: http://localhost:8081 (dev only)

## Architecture Overview

```mermaid
graph TB
    subgraph "Single Docker Container"
        subgraph "Services"
            API[FastAPI Backend<br/>:8000]
            VNC[VNC Server<br/>:5900]
            NOVNC[noVNC Web Interface<br/>:8080]
        end
        
        subgraph "Storage"
            DB[SQLite Database<br/>/home/computeruse/data]
            LOGS[Application Logs<br/>/home/computeruse/logs]
        end
        
        API --> DB
        VNC --> NOVNC
    end
    
    Client --> API
    Client --> NOVNC
    Client --> WEBAPP
    
    subgraph "External Volumes"
        VDATA[comp_use_data]
        VLOGS[comp_use_logs]
    end
    
    DB --> VDATA
    LOGS --> VLOGS
```

## Container Services

### Unified Service (`comp_use_service`)
- **Image**: Built from `Dockerfile`
- **Ports**: 
  - 8000 (FastAPI Backend)
  - 8080 (noVNC Web Interface)
  - 5900 (VNC Server)
- **Features**:
  - Complete desktop environment with Ubuntu 22.04
  - FastAPI backend with WebSocket support
  - Computer use agent integration
  - noVNC web interface for visual monitoring
  - Web-based frontend interface
  - Health checks and logging

## Deployment Configurations

### Development Environment

**Command**:
```bash
# Automated setup
./docker-setup.sh

# Manual setup
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up
```

**Features**:
- Hot reloading for FastAPI backend
- Debug logging enabled
- Database viewer accessible
- Volume mounts for live code editing
- Development-friendly startup sequence

**Environment Variables**:
```env
FASTAPI_ENV=development
LOG_LEVEL=debug
ANTHROPIC_API_KEY=your-key-here
DATABASE_URL=sqlite:///home/computeruse/data/sessions.db
```

### Production Environment

**Command**:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Features**:
- Optimized container configuration
- Resource limits and reservations
- Security optimizations
- Database viewer disabled
- Structured logging with rotation

**Environment Variables**:
```env
FASTAPI_ENV=production
LOG_LEVEL=info
ANTHROPIC_API_KEY=your-key-here
DATABASE_URL=sqlite:///home/computeruse/data/sessions.db
```

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Anthropic API key for agent | `sk-ant-api...` |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:comp_use_password@postgres:5432/postgres` | Database connection string |
| `LOG_LEVEL` | `info` | Logging level |
| `FASTAPI_ENV` | `production` | Environment mode |
| `DISPLAY_NUM` | `1` | VNC display number |
| `WIDTH` | `1024` | Desktop width |
| `HEIGHT` | `768` | Desktop height |

## Volume Management

### Persistent Volumes

- `comp_use_data`: SQLite database and application data
- `comp_use_logs`: Application and service logs

### Backup Strategy

```bash
# Backup database and data
docker run --rm -v comp_use_agent_comp_use_data:/data -v $(pwd):/backup alpine tar czf /backup/data-$(date +%Y%m%d).tar.gz /data

# Restore database and data
docker run --rm -v comp_use_agent_comp_use_data:/data -v $(pwd):/backup alpine tar xzf /backup/data-YYYYMMDD.tar.gz -C /
```

## Health Checks

The unified service includes comprehensive health checks:

- **FastAPI Backend**: `GET /health` endpoint check
- **noVNC Interface**: HTTP check on port 8080

Check service health:
```bash
docker-compose ps
docker-compose logs comp_use_service
```

## Performance Tuning

### Resource Limits (Production)

```yaml
# Unified service
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
    reservations:
      cpus: '1.0'
      memory: 1G
```

### Scaling

The unified architecture doesn't support horizontal scaling, but you can adjust resource limits or run multiple independent instances on different ports.

## Security Best Practices

### Container Security
- Non-root user in container
- Security options enabled
- Minimal attack surface
- Health monitoring

### Network Security
- No external reverse proxy needed
- Direct port exposure with Docker's built-in security
- Isolated container environment

### Data Security
- Volume encryption (configure at Docker daemon level)
- Environment variable protection
- API key management

## Troubleshooting

### Common Issues

**1. Port conflicts**
```bash
# Check port usage
netstat -tulpn | grep :8000
# Kill conflicting processes
sudo fuser -k 8000/tcp
```

**2. Container won't start**
```bash
# Check logs
docker-compose logs comp_use_service
# Debug container
docker-compose exec comp_use_service bash
```

**3. Database connection issues**
```bash
# Check database volume
docker volume inspect comp_use_agent_comp_use_data
# Access database directly
docker-compose exec comp_use_service sqlite3 /home/computeruse/data/sessions.db
```

**4. VNC connection problems**
```bash
# Check VNC processes
docker-compose exec comp_use_service ps aux | grep vnc
# Check VNC logs
docker-compose exec comp_use_service tail -f /tmp/server_logs.txt
```

**5. FastAPI backend issues**
```bash
# Check FastAPI logs
docker-compose exec comp_use_service tail -f /tmp/fastapi.log
# Restart FastAPI only
docker-compose exec comp_use_service pkill -f uvicorn
```

### Debugging Commands

```bash
# View all logs
docker-compose logs -f comp_use_service

# Access container shell
docker-compose exec comp_use_service bash

# Check running processes
docker-compose exec comp_use_service ps aux

# Monitor resource usage
docker stats

# Inspect container configuration
docker inspect comp_use_unified
```

### Log Analysis

```bash
# FastAPI backend logs
docker-compose exec comp_use_service tail -f /tmp/fastapi.log

# VNC/noVNC logs
docker-compose exec comp_use_service tail -f /tmp/server_logs.txt

# Health check failures
docker-compose logs comp_use_service | grep healthcheck
```

## Monitoring

### Health Monitoring
```bash
# Check service health
docker-compose ps

# Continuous health monitoring
watch -n 5 'docker-compose ps'

# Check individual service health
curl http://localhost:8000/health
curl http://localhost:8080
```

### Log Monitoring
```bash
# Real-time log monitoring
docker-compose logs -f comp_use_service --tail=50

# Error log monitoring
docker-compose logs comp_use_service | grep -i error
```

## Maintenance

### Updates
```bash
# Pull latest base images
docker-compose pull

# Rebuild and restart
docker-compose build --no-cache
docker-compose up -d
```

### Cleanup
```bash
# Remove unused containers and images
docker system prune -f

# Remove specific volumes (careful!)
docker volume rm comp_use_agent_comp_use_data
```

## Production Checklist

- [ ] Environment variables configured
- [ ] ANTHROPIC_API_KEY set
- [ ] Resource limits configured
- [ ] Backup strategy implemented
- [ ] Health checks verified
- [ ] Log monitoring configured
- [ ] Database backup tested
- [ ] Container security verified

## Support

For additional support:
1. Check container logs: `docker-compose logs comp_use_service`
2. Review health checks: `docker-compose ps`
3. Access container shell: `docker-compose exec comp_use_service bash`
4. Check resource usage: `docker stats`
5. Consult the main project documentation 