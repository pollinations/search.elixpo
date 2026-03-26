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

COMPOSE_FILE="docker-compose.yml"

# Only validate container count for commands that use it
case "${1:-help}" in
    start|scale|stary|quick)
        CONTAINER_COUNT=${2:-3}
        if ! [[ "$CONTAINER_COUNT" =~ ^[0-9]+$ ]]; then
            echo -e "${RED}✗${NC} Container count must be a number"
            exit 1
        fi
        ;;
esac

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
        error ".env file not found in root directory"
        info "Use the root .env file with:"
        echo "  TOKEN=your_token"
        echo "  MODEL=your_model"
        echo "  IMAGE_MODEL=your_image_model"
        echo "  HF_TOKEN=your_hf_token"
        exit 1
    fi
}

check_docker() {
    if ! command -v docker compose &> /dev/null; then
        error "docker compose is not installed"
        exit 1
    fi
}

start_services() {
    local count=$1
    check_env
    check_docker

    info "Starting lixSearch with $count container(s)..."

    if [ "$count" -eq 1 ]; then
        docker compose -f "$COMPOSE_FILE" up -d --remove-orphans
    else
        docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --scale lixsearch-app="$count"
    fi

    info "Waiting for services to be healthy (90 seconds)..."
    sleep 90

    success "Services started"
    show_status
}

build_image() {
    local no_cache=${1:-false}
    check_docker

    info "Building lixSearch image..."
    
    if [ "$no_cache" = "true" ]; then
        info "Building with --no-cache flag (smallest image)..."
        docker compose -f "$COMPOSE_FILE" build --no-cache
    else
        docker compose -f "$COMPOSE_FILE" build
    fi

    success "Image built successfully"
}

scale_containers() {
    local count=$1
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        error "Scale count must be a number"
        exit 1
    fi
    check_docker

    info "Scaling to $count container(s)..."
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --scale lixsearch-app="$count"

    sleep 10
    success "Scaled to $count container(s)"
    show_status
}

stop_services() {
    check_docker
    info "Stopping all services..."
    docker compose -f "$COMPOSE_FILE" down --remove-orphans
    success "Services stopped"
}

clean_volumes() {
    check_docker
    warning "This will delete all data (Redis, Chroma, Nginx cache)"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        info "Removing containers and volumes..."
        docker compose -f "$COMPOSE_FILE" down -v --remove-orphans
        success "Cleaned up"
    fi
}

show_status() {
    echo ""
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
}

show_logs() {
    local service=${1:-nginx}
    check_docker

    case "$service" in
        app|lixsearch)
            docker compose -f "$COMPOSE_FILE" logs -f lixsearch-app
            ;;
        redis)
            docker compose -f "$COMPOSE_FILE" logs -f redis
            ;;
        chroma)
            docker compose -f "$COMPOSE_FILE" logs -f chroma-server
            ;;
        *)
            docker compose -f "$COMPOSE_FILE" logs -f nginx
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

    if docker compose -f "$COMPOSE_FILE" exec redis redis-cli ping > /dev/null 2>&1; then
        success "Redis: HEALTHY"
    else
        error "Redis: UNREACHABLE"
    fi

    if docker compose -f "$COMPOSE_FILE" exec chroma-server curl -s http://localhost:8000/api/version > /dev/null 2>&1; then
        success "Chroma: HEALTHY"
    else
        error "Chroma: UNREACHABLE"
    fi

    echo ""
}

restart_services() {
    check_docker
    info "Restarting all services..."
    docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --force-recreate
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
    docker compose -f "$COMPOSE_FILE" exec redis redis-cli BGSAVE > /dev/null 2>&1

    sleep 2

    docker compose -f "$COMPOSE_FILE" cp redis:/data/dump.rdb \
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

_bump_version() {
    local pyproject=$1
    local bump_type=$2
    local current=$(grep '^version' "$pyproject" | sed 's/version = "\(.*\)"/\1/')
    IFS='.' read -r major minor patch <<< "$current"
    case "$bump_type" in
        major) major=$((major + 1)); minor=0; patch=0 ;;
        minor) minor=$((minor + 1)); patch=0 ;;
        patch) patch=$((patch + 1)) ;;
    esac
    echo "${major}.${minor}.${patch}"
}

_build_and_upload_pypi() {
    local pkg_dir=$1
    local pkg_name=$2
    local new_version=$3

    info "Building ${pkg_name}..."
    cd "$pkg_dir"
    rm -rf dist/ build/ *.egg-info
    python -m build
    cd ..
    success "Built dist files"

    info "Uploading ${pkg_name} to PyPI..."
    twine upload "${pkg_dir}/dist/*"
    success "Published ${pkg_name} ${new_version} to PyPI"
}

_github_release() {
    local tag=$1
    local title=$2
    local notes=$3
    shift 3
    local assets=("$@")

    if ! command -v gh &> /dev/null; then
        warning "gh CLI not installed — skipping GitHub release"
        info "Install: https://cli.github.com"
        return 1
    fi

    info "Creating GitHub release ${tag}..."
    git add -A
    git commit -m "release: ${title}"
    git tag "$tag"
    git push origin main --tags
    gh release create "$tag" "${assets[@]}" \
        --title "$title" \
        --notes "$notes"
    success "GitHub release ${tag} created"
}

_get_version() {
    grep '^version' package/pyproject.toml | sed 's/version = "\(.*\)"/\1/'
}

_release_notes() {
    local v=$1
    cat <<NOTES
## lix-open-search v${v}

Python SDK + caching library for lixSearch — multi-tool AI search with web, video, image, deep research, and production-grade session caching.

### Install

\`\`\`bash
pip install lix-open-search==${v}
\`\`\`

### Includes

**lix_open_search** — Client SDK
\`\`\`python
from lix_open_search import LixSearch

lix = LixSearch("http://localhost:9002")
result = lix.search("quantum computing breakthroughs 2026")

for chunk in lix.search_stream("latest AI papers"):
    print(chunk.content, end="", flush=True)
\`\`\`

**lix_open_cache** — Multi-layer caching
\`\`\`python
from lix_open_cache import CacheConfig, CacheCoordinator

config = CacheConfig(redis_host="localhost", redis_port=6379)
cache = CacheCoordinator(session_id="user-abc", config=config)
cache.add_message_to_context("user", "What's the weather in Tokyo?")
\`\`\`

### Self-host with Docker

\`\`\`bash
docker pull ghcr.io/circuit-overtime/lix-open-search:${v}
docker compose -f package/docker-compose.yml up -d
\`\`\`

### Features

- **Search SDK**: sync + async clients, streaming, multi-turn sessions, multimodal
- **Cache library**: 3-layer Redis caching, Huffman disk archival, LRU eviction
- **OpenAI-compatible** — drop-in replacement for OpenAI Python client
- **Docker**: self-host the full engine on any server

### Links

- [PyPI](https://pypi.org/project/lix-open-search/${v}/)
- [Docker Hub](https://hub.docker.com/r/elixpo/lix-open-search)
- [GHCR](https://github.com/Circuit-Overtime/lixSearch/pkgs/container/lix-open-search)
- [Docs](https://github.com/Circuit-Overtime/lixSearch/blob/main/package/README.md)
- [Research Paper](https://github.com/Circuit-Overtime/lixSearch/blob/main/docs/paper/lix_cache_paper.pdf)
- [Live Demo](https://search.elixpo.com)
NOTES
}

# ── Fine-grained release commands ──────────────────────

release_bump() {
    local bump_type=${1:-patch}
    local pyproject="package/pyproject.toml"
    local current=$(_get_version)
    local new_version=$(_bump_version "$pyproject" "$bump_type")

    sed -i "s/^version = \".*\"/version = \"${new_version}\"/" "$pyproject"
    sed -i "s/^__version__ = \".*\"/__version__ = \"${new_version}\"/" package/lix_open_search/__init__.py 2>/dev/null || true

    success "Version bumped: ${current} → ${new_version}"
}

release_build() {
    local version=$(_get_version)
    info "Building package v${version}..."
    cd package
    rm -rf dist/ build/ *.egg-info
    python -m build
    cd ..
    success "Built package/dist/ (v${version})"
}

release_pypi() {
    local version=$(_get_version)
    if [ ! -d "package/dist" ]; then
        release_build
    fi
    info "Uploading lix-open-search v${version} to PyPI..."
    twine upload package/dist/*
    success "Published to PyPI: pip install lix-open-search==${version}"
}

release_github() {
    local version=$(_get_version)
    local notes=$(_release_notes "$version")

    if ! command -v gh &> /dev/null; then
        error "gh CLI not installed (https://cli.github.com)"
        exit 1
    fi

    info "Creating GitHub release v${version}..."
    git add package/pyproject.toml package/lix_open_search/__init__.py 2>/dev/null
    git commit -m "release: lix-open-search v${version}" 2>/dev/null || true
    git tag -f "v${version}"
    git push origin main --tags

    local assets=()
    if [ -d "package/dist" ]; then
        assets=(package/dist/*)
    fi

    gh release create "v${version}" "${assets[@]}" \
        --title "lix-open-search v${version}" \
        --notes "$notes"
    success "GitHub release v${version} created"
}

release_docker() {
    # Load credentials from .env
    if [ -f ".env" ]; then
        set -a
        source .env
        set +a
    fi

    # Validate required vars
    if [ -z "$GITHUB_TOKEN" ]; then
        error "GITHUB_TOKEN not set in .env"
        exit 1
    fi
    if [ -z "$DOCKER_HUB_API" ]; then
        warning "DOCKER_HUB_API not set in .env — skipping Docker Hub push"
    fi

    local ghcr_image="ghcr.io/${GITHUB_USER:-Circuit-Overtime}/lix-open-search"
    local hub_image="${DOCKERHUB_USER:-elixpo}/lix-open-search"
    local version=$(_get_version)
    info "Building Docker image v${version}"

    check_docker

    # Build with all tags at once (context is repo root, Dockerfile in package/)
    docker build -f package/Dockerfile \
        -t "${ghcr_image}:${version}" \
        -t "${ghcr_image}:latest" \
        -t "${hub_image}:${version}" \
        -t "${hub_image}:latest" \
        .
    success "Built image v${version}"

    # Push to GitHub Container Registry
    info "Pushing to ghcr.io..."
    echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GITHUB_USER:-elixpo}" --password-stdin
    docker push "${ghcr_image}:${version}"
    docker push "${ghcr_image}:latest"
    success "Pushed ${ghcr_image}:${version}"

    # Push to Docker Hub
    if [ -n "$DOCKER_HUB_API" ]; then
        info "Pushing to Docker Hub..."
        echo "${DOCKER_HUB_API}" | docker login -u "${DOCKERHUB_USER:-elixpo}" --password-stdin
        docker push "${hub_image}:${version}"
        docker push "${hub_image}:latest"
        success "Pushed ${hub_image}:${version}"
    fi

    echo ""
    success "Docker image v${version} published"
    info "GHCR: docker pull ${ghcr_image}:${version}"
    info "Hub:  docker pull ${hub_image}:${version}"
    info "Run:  docker compose -f package/docker-compose.yml up -d"
}

release_all() {
    local bump_type=${1:-patch}
    info "Full release (${bump_type} bump)..."
    echo ""

    release_bump "$bump_type"
    release_build
    echo ""
    release_pypi
    echo ""
    release_docker
    echo ""
    release_github

    echo ""
    local v=$(_get_version)
    success "All released: lix-open-search v${v}"
    info "PyPI:   pip install lix-open-search==${v}"
    info "Docker: docker pull elixpo/lix-open-search:${v}"
}

show_help() {
    cat << EOF
${BLUE}lixSearch Production Deployment Helper${NC}

${YELLOW}Usage:${NC}
  ./deploy.sh COMMAND [ARGS]

${YELLOW}Commands:${NC}
  build [no-cache]  Build image (add 'no-cache' for --no-cache flag)
  stary [N]         Build with cache + start (default 3 containers)
  quick [N]         Rebuild app only + rolling restart (infra/dep changes)
  hotfix            Copy code into running containers + restart (fastest, code-only)
  start [N]         Start services (N containers, default 3)
  scale N           Scale to N containers
  stop              Stop all services
  restart           Restart all services
  health            Check service health
  logs [SERVICE]    Show logs (nginx|app|redis|chroma)
  backup            Backup Redis data
  clean             Remove all data (volumes)
  test-scale        Test scalability (1→2→3→5 containers)
  release <sub>       Package release (run ./deploy.sh release for details)
                      sub: version | bump | build | pypi | docker | github | all
  help              Show this help message

${YELLOW}Examples:${NC}
  ./deploy.sh build                       # Build with cache
  ./deploy.sh build no-cache              # Build smallest image (no-cache)
  ./deploy.sh start                       # Start single container
  ./deploy.sh start 3                     # Start with 3 containers
  ./deploy.sh scale 5                     # Scale to 5 containers
  ./deploy.sh logs app                    # View app logs
  ./deploy.sh health                      # Check all services
  ./deploy.sh backup                      # Backup Redis
  ./deploy.sh release version              # Check package version
  ./deploy.sh release bump minor          # Bump version only
  ./deploy.sh release pypi                # Upload to PyPI
  ./deploy.sh release docker              # Push Docker to ghcr.io + Docker Hub
  ./deploy.sh release all                 # Full release (bump + build + everything)

${YELLOW}Environment:${NC}
  Use the root .env file with required variables:
    TOKEN=your_token
    MODEL=your_model
    IMAGE_MODEL=your_image_model
    HF_TOKEN=your_hf_token

${YELLOW}Quick Start:${NC}
  1. Ensure .env exists in root directory
  2. ./deploy.sh build no-cache
  3. ./deploy.sh start 3
  4. ./deploy.sh health

EOF
}

case "${1:-help}" in
    build)
        build_image "$2"
        ;;
    start)
        start_services "$CONTAINER_COUNT"
        ;;
    stary)
        info "Build + start with ${CONTAINER_COUNT} containers..."
        build_image "false"
        start_services "$CONTAINER_COUNT"
        ;;
    quick)
        info "Quick restart — rebuild app image only, rolling restart..."
        check_env
        check_docker
        docker compose -f "$COMPOSE_FILE" build lixsearch-app
        docker compose -f "$COMPOSE_FILE" up -d --remove-orphans --no-deps --scale lixsearch-app="${CONTAINER_COUNT}" lixsearch-app
        info "Waiting for health..."
        sleep 30
        success "App containers restarted (${CONTAINER_COUNT} replicas)"
        show_status
        ;;
    hotfix)
        info "Hotfix — copying code into running containers (no rebuild)..."
        check_docker
        containers=$(docker compose -f "$COMPOSE_FILE" ps -q lixsearch-app 2>/dev/null)
        if [ -z "$containers" ]; then
            error "No running app containers found"
            exit 1
        fi
        count=0
        for cid in $containers; do
            cname=$(docker inspect --format '{{.Name}}' "$cid" | sed 's|^/||')
            docker cp lixsearch/. "$cid":/app/lixsearch/
            docker cp openapi.yaml "$cid":/app/openapi.yaml
            docker cp public/. "$cid":/app/public/
            info "  Updated $cname"
            count=$((count + 1))
        done
        # Also update ipc-service if running
        ipc_cid=$(docker compose -f "$COMPOSE_FILE" ps -q ipc-service 2>/dev/null)
        if [ -n "$ipc_cid" ]; then
            docker cp lixsearch/. "$ipc_cid":/app/lixsearch/
            info "  Updated ipc-service"
        fi
        info "Restarting $count app container(s)..."
        docker compose -f "$COMPOSE_FILE" restart lixsearch-app
        sleep 15
        success "Hotfix applied to $count container(s)"
        show_status
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
    release)
        case "${2:-help}" in
            bump)   release_bump "$3" ;;
            build)  release_build ;;
            pypi)   release_pypi ;;
            docker) release_docker ;;
            github) release_github ;;
            all)    release_all "$3" ;;
            version) info "Current version: $(_get_version)" ;;
            *)
                cat <<RELEASE_HELP
${YELLOW}Usage:${NC} ./deploy.sh release <command> [args]

${YELLOW}Commands:${NC}
  version              Show current package version
  bump [TYPE]          Bump version only (patch|minor|major, default: patch)
  build                Build .whl + .tar.gz (no upload)
  pypi                 Upload to PyPI (builds first if needed)
  docker               Build + push Docker image to ghcr.io + Docker Hub
  github               Create GitHub release with notes + assets
  all [TYPE]           Full release: bump + build + PyPI + Docker + GitHub

${YELLOW}Examples:${NC}
  ./deploy.sh release version          # Check current version
  ./deploy.sh release bump minor       # 0.1.0 → 0.2.0
  ./deploy.sh release build            # Build without uploading
  ./deploy.sh release pypi             # Upload current build to PyPI
  ./deploy.sh release docker           # Push Docker image only
  ./deploy.sh release github           # Create GitHub release only
  ./deploy.sh release all              # Everything (patch bump)
  ./deploy.sh release all minor        # Everything (minor bump)
RELEASE_HELP
                ;;
        esac
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
