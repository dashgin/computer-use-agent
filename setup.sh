#!/bin/bash

# Computer Use Session Backend Setup Script
# Author: Dashgin Khudiyev

set -e  # Exit on any error

echo "🚀 Computer Use Session Backend Setup"
echo "===================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed and running
check_docker() {
    print_status "Checking Docker installation..."
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        echo "Visit: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        print_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi
    
    print_success "Docker is installed and running"
}

# Create .env file if it doesn't exist
setup_env() {
    print_status "Setting up environment configuration..."
    
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_success "Created .env file from .env.example"
        else
            print_warning ".env.example not found, creating basic .env file"
            cat > .env << EOF
# Anthropic API Configuration
ANTHROPIC_API_KEY=

# Application Configuration
FASTAPI_ENV=development
LOG_LEVEL=info

# Database Configuration
DATABASE_URL=postgresql+asyncpg://postgres:comp_use_password@postgres:5432/postgres

# VNC Configuration
DISPLAY_NUM=1
WIDTH=1024
HEIGHT=768
EOF
            print_success "Created basic .env file"
        fi
    else
        print_success ".env file already exists"
    fi
}

# Check ANTHROPIC_API_KEY
check_api_key() {
    print_status "Checking Anthropic API key configuration..."
    
    # Check environment variable
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        print_success "ANTHROPIC_API_KEY found in environment"
        return 0
    fi
    
    # Check .env file
    if [ -f ".env" ] && grep -q "ANTHROPIC_API_KEY=sk-" .env; then
        print_success "ANTHROPIC_API_KEY found in .env file"
        return 0
    fi
    
    print_warning "ANTHROPIC_API_KEY not configured"
    echo ""
    echo "To enable full AI functionality, you need to set your Anthropic API key."
    echo "You can:"
    echo ""
    echo "1. Set environment variable:"
    echo "   export ANTHROPIC_API_KEY='your-api-key-here'"
    echo ""
    echo "2. Or add it to .env file:"
    echo "   echo 'ANTHROPIC_API_KEY=your-api-key-here' >> .env"
    echo ""
    echo "Get your API key from: https://console.anthropic.com/"
    echo ""
    read -p "Do you want to set it now? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter your Anthropic API key: " -s api_key
        echo
        if [ -n "$api_key" ]; then
            # Update .env file
            sed -i.bak "s/ANTHROPIC_API_KEY=.*/ANTHROPIC_API_KEY=$api_key/" .env
            print_success "API key added to .env file"
        else
            print_warning "No API key entered, continuing without it"
        fi
    else
        print_warning "Continuing without API key - agent will run in echo mode"
    fi
}

# Build and start services
start_services() {
    print_status "Building and starting services..."
    
    # Pull latest images
    print_status "Pulling required Docker images..."
    docker-compose pull postgres
    
    # Build application image
    print_status "Building application container..."
    docker-compose build comp_use_service
    
    # Start services
    print_status "Starting services..."
    docker-compose up -d
    
    print_success "Services started"
}

# Wait for services to be ready
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for database
    print_status "Waiting for database..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if docker-compose exec -T postgres pg_isready -U postgres &> /dev/null; then
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "Database failed to start within 60 seconds"
        exit 1
    fi
    
    # Wait for API
    print_status "Waiting for API server..."
    timeout=60
    while [ $timeout -gt 0 ]; do
        if curl -s http://localhost:8000/api &> /dev/null; then
            break
        fi
        sleep 2
        timeout=$((timeout - 2))
    done
    
    if [ $timeout -le 0 ]; then
        print_error "API server failed to start within 60 seconds"
        print_error "Check logs: docker-compose logs comp_use_service"
        exit 1
    fi
    
    print_success "All services are ready"
}

# Run health checks
health_check() {
    print_status "Running health checks..."
    
    # API health check
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        print_success "API health check passed"
    else
        print_warning "API health check failed"
        echo "Check logs: docker-compose logs comp_use_service"
    fi
    
    # VNC health check
    if curl -s http://localhost:8000/api/vnc/status | grep -q "true"; then
        print_success "VNC health check passed"
    else
        print_warning "VNC health check failed"
        echo "VNC may take additional time to start"
    fi
    
    # Database health check
    if docker-compose exec -T postgres pg_isready -U postgres &> /dev/null; then
        print_success "Database health check passed"
    else
        print_warning "Database health check failed"
    fi
}

# Show access information
show_access_info() {
    echo ""
    echo "🎉 Setup Complete!"
    echo "=================="
    echo ""
    echo "Access your application:"
    echo "📱 Frontend UI:        http://localhost:8000"
    echo "📚 API Documentation:  http://localhost:8000/docs"
    echo "🖥️  VNC Desktop:        http://localhost:6080"
    echo "❤️  Health Check:       http://localhost:8000/health"
    echo ""
    echo "Useful commands:"
    echo "🔍 Check status:        docker-compose ps"
    echo "📜 View logs:           docker-compose logs -f comp_use_service"
    echo "🛑 Stop services:       docker-compose down"
    echo "🔄 Restart services:    docker-compose restart"
    echo ""
    
    if [ -z "${ANTHROPIC_API_KEY:-}" ] && ! grep -q "ANTHROPIC_API_KEY=sk-" .env 2>/dev/null; then
        print_warning "Remember to set your ANTHROPIC_API_KEY for full functionality!"
        echo "Run: echo 'ANTHROPIC_API_KEY=your-key-here' >> .env"
        echo "Then: docker-compose restart comp_use_service"
        echo ""
    fi
    
    echo "🎬 Ready for demo? Follow the guide in DEMO_VIDEO.md"
    echo "📖 For more details, see README.md"
}

# Main execution
main() {
    echo ""
    check_docker
    setup_env
    check_api_key
    start_services
    wait_for_services
    health_check
    show_access_info
}

# Handle script interruption
cleanup() {
    echo ""
    print_warning "Setup interrupted"
    echo "To clean up, run: docker-compose down"
    exit 1
}

trap cleanup INT TERM

# Run main function
main

echo ""
print_success "Setup completed successfully! 🚀" 