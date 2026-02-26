#!/bin/bash

# Usage:
#   ./deploy.sh start              # Start single container
#   ./deploy.sh start 3            # Start with 3 containers
#   ./deploy.sh scale 5            # Scale to 5 containers
#   ./deploy.sh stop               # Stop all containers
#   ./deploy.sh logs               # View nginx logs
#   ./deploy.sh logs app           # View app logs
#   ./deploy.sh health             # Check all services
#   ./deploy.sh restart            # Restart all services
#   ./deploy.sh clean              # Clean up volumes
#   ./deploy.sh backup             # Backup Redis data

set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.prod.yml"
CONTAINER_COUNT=${2:-1}

info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

check_env() {
    if [ ! -f ".env" ]; then
        error ".env file not found"
        info "Copy .env.prod to .env and customize:"
        echo "  cp .env.prod .env"
        echo "  nano .env"
        exit 1
    fi
}

check_docker() {
    if ! command -v docker-compose &> /dev/null; then
        error "docker-compose is not installed"
        exit 1
    fi
}

start_services() {
    local count=$1
    check_env
    check_docker

    info "Starting lixSearch with $count container(s)..."

    if [ "$count" -eq 1 ]; then
        docker-compose -f "$COMPOSE_FILE" up -d
    else
        docker-compose -f "$COMPOSE_FILE" up -d --scale lixsearch-app="$count"
    fi

    info "Waiting for services to be healthy (30 seconds)..."
    sleep 30

    success "Services started"
    show_status
}

scale_containers() {
    local count=$1
    check_docker

    info "Scaling to $count container(s)..."
    docker-compose -f "$COMPOSE_FILE" up -d --scale lixsearch-app="$count"

    sleep 10
    success "Scaled to $count container(s)"
    show_status
}

stop_services() {
    check_docker
    info "Stopping all services..."
    docker-compose -f "$COMPOSE_FILE" down
    success "Services stopped"
}

clean_volumes() {
    check_docker
    warning "This will delete all data (Redis, Chroma, Nginx cache)"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Removing containers and volumes..."
        docker-compose -f "$COMPOSE_FILE" down -v
        success "Cleaned up"
    fi
}

show_status() {
    echo ""
    docker-compose -f "$COMPOSE_FILE" ps
    echo ""
}

show_logs() {
    local service=${1:-nginx}
    check_docker

    case "$service" in
        app|lixsearch)
            docker-compose -f "$COMPOSE_FILE" logs -f lixsearch-app
            ;;
        redis)
            docker-compose -f "$COMPOSE_FILE" logs -f redis
            ;;
        chroma)
            docker-compose -f "$COMPOSE_FILE" logs -f chroma-server
            ;;
        *)
            docker-compose -f "$COMPOSE_FILE" logs -f nginx
            ;;
    esac
}

check_health() {
    check_docker
    echo ""
    info "Service Status:"
    show_status

    echo ""
    info "Health Checks:"

    if curl -s http://localhost/api/health > /dev/null 2>&1; then
        success "Nginx & API: HEALTHY"
    else
        error "Nginx & API: UNREACHABLE"
    fi

    if docker-compose -f "$COMPOSE_FILE" exec redis redis-cli ping > /dev/null 2>&1; then
        success "Redis: HEALTHY"
    else
        error "Redis: UNREACHABLE"
    fi

    if docker-compose -f "$COMPOSE_FILE" exec chroma-server curl -s http://localhost:8000/api/version > /dev/null 2>&1; then
        success "Chroma: HEALTHY"
    else
        error "Chroma: UNREACHABLE"
    fi

    echo ""
}

restart_services() {
    check_docker
    info "Restarting all services..."
    docker-compose -f "$COMPOSE_FILE" restart
    sleep 10
    success "Services restarted"
    check_health
}

backup_redis() {
    check_docker
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_dir="backups"

    mkdir -p "$backup_dir"

    info "Backing up Redis data..."
    docker-compose -f "$COMPOSE_FILE" exec redis redis-cli BGSAVE > /dev/null 2>&1

    sleep 2

    docker-compose -f "$COMPOSE_FILE" cp redis:/data/dump.rdb \
        "$backup_dir/redis_dump_${timestamp}.rdb" 2>/dev/null || true

    success "Redis backed up to $backup_dir/redis_dump_${timestamp}.rdb"

    ls -t "$backup_dir"/redis_dump_* | tail -n +11 | xargs -r rm
}

test_scaling() {
    check_docker

    echo ""
    info "Testing scalability from 1 to 5 containers..."

    for count in 1 2 3 5; do
        info "Scaling to $count container(s)..."
        scale_containers "$count"

        sleep 5
        response=$(curl -s -w "\n%{http_code}" http://localhost/api/health)
        status=$(echo "$response" | tail -n1)

        if [ "$status" = "200" ]; then
            success "✓ $count container(s) - healthy"
        else
            error "✗ $count container(s) - unhealthy (HTTP $status)"
        fi
    done

    info "Scaling test complete"
    echo ""
}

show_help() {
    cat << EOF
${BLUE}lixSearch Production Deployment Helper${NC}

${YELLOW}Usage:${NC}
  ./deploy.sh COMMAND [ARGS]

${YELLOW}Commands:${NC}
  start [N]         Start services (N containers, default 1)
  scale N           Scale to N containers
  stop              Stop all services
  restart           Restart all services
  health            Check service health
  logs [SERVICE]    Show logs (nginx|app|redis|chroma)
  backup            Backup Redis data
  clean             Remove all data (volumes)
  test-scale        Test scalability (1→2→3→5 containers)
  help              Show this help message

${YELLOW}Examples:${NC}
  ./deploy.sh start                    # Start single container
  ./deploy.sh start 3                  # Start with 3 containers
  ./deploy.sh scale 5                  # Scale to 5 containers
  ./deploy.sh logs app                 # View app logs
  ./deploy.sh health                   # Check all services
  ./deploy.sh backup                   # Backup Redis

${YELLOW}Environment:${NC}
  Copy .env.prod to .env and customize before running:
    cp .env.prod .env
    nano .env

${YELLOW}Quick Start:${NC}
  1. cp .env.prod .env
  2. nano .env
  3. ./deploy.sh start
  4. curl http://localhost/api/health

EOF
}

case "${1:-help}" in
    start)
        start_services "$CONTAINER_COUNT"
        ;;
    scale)
        if [ -z "$2" ]; then
            error "scale requires a number (e.g., ./deploy.sh scale 3)"
            exit 1
        fi
        scale_containers "$2"
        ;;
    stop)
        stop_services
        ;;
    restart)
        restart_services
        ;;
    health)
        check_health
        ;;
    logs)
        show_logs "$2"
        ;;
    backup)
        backup_redis
        ;;
    clean)
        clean_volumes
        ;;
    test-scale)
        test_scaling
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
