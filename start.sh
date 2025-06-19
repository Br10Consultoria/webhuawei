#!/bin/bash

# 🚀 NE8000 Monitor - Script de Inicialização
# Este script facilita o uso do sistema Docker

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função para imprimir mensagens coloridas
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Verificar se Docker está instalado
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker não está instalado!"
        echo "Por favor, instale o Docker primeiro: https://docs.docker.com/get-docker/"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose não está instalado!"
        echo "Por favor, instale o Docker Compose primeiro"
        exit 1
    fi
    
    print_success "Docker e Docker Compose encontrados"
}

# Verificar arquivo .env
check_env() {
    if [ ! -f ".env" ]; then
        print_warning "Arquivo .env não encontrado!"
        if [ -f ".env.example" ]; then
            print_info "Copiando .env.example para .env..."
            cp .env.example .env
            print_warning "Configure o arquivo .env com suas informações antes de continuar!"
            echo "Editores sugeridos: nano .env, vim .env, ou code .env"
            return 1
        else
            print_error "Arquivo .env.example também não encontrado!"
            return 1
        fi
    fi
    print_success "Arquivo .env encontrado"
    return 0
}

# Função para mostrar status
show_status() {
    print_info "Status dos containers:"
    docker-compose ps
    echo ""
    print_info "Logs recentes:"
    docker-compose logs --tail=10 app
}

# Função para mostrar URLs
show_urls() {
    echo ""
    print_success "🌐 Aplicação iniciada com sucesso!"
    echo "────────────────────────────────────────────"
    echo "🏠 Dashboard Principal: http://localhost:8000"
    echo "⚡ Dashboard Híbrido:   http://localhost:8000/hybrid"
    echo "🏥 Health Check:        http://localhost:8000/health"
    echo "📊 Cache Stats:         http://localhost:8000/api/cache_stats"
    echo "────────────────────────────────────────────"
    echo ""
    print_info "Comandos úteis:"
    echo "  Ver logs:      docker-compose logs -f app"
    echo "  Parar:         docker-compose down"
    echo "  Reiniciar:     docker-compose restart app"
    echo "  Status:        docker-compose ps"
}

# Função principal
main() {
    echo "🚀 NE8000 Sistema Híbrido de Monitoramento"
    echo "═══════════════════════════════════════════"
    
    # Verificações
    check_docker
    
    if ! check_env; then
        exit 1
    fi
    
    case "${1:-start}" in
        "start")
            print_info "Iniciando aplicação..."
            docker-compose up --build -d
            
            print_info "Aguardando inicialização..."
            sleep 10
            
            # Verificar se está rodando
            if docker-compose ps | grep -q "Up"; then
                show_urls
            else
                print_error "Falha ao iniciar a aplicação!"
                print_info "Verificando logs de erro..."
                docker-compose logs app
                exit 1
            fi
            ;;
            
        "stop")
            print_info "Parando aplicação..."
            docker-compose down
            print_success "Aplicação parada"
            ;;
            
        "restart")
            print_info "Reiniciando aplicação..."
            docker-compose restart app
            sleep 5
            show_status
            ;;
            
        "status")
            show_status
            ;;
            
        "logs")
            print_info "Mostrando logs (Ctrl+C para sair)..."
            docker-compose logs -f app
            ;;
            
        "update")
            print_info "Atualizando aplicação..."
            docker-compose down
            docker-compose build --no-cache app
            docker-compose up -d
            print_success "Aplicação atualizada"
            show_urls
            ;;
            
        "clean")
            print_warning "Removendo containers, imagens e volumes..."
            read -p "Tem certeza? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                docker-compose down -v --rmi all
                print_success "Limpeza concluída"
            else
                print_info "Operação cancelada"
            fi
            ;;
            
        "help"|"-h"|"--help")
            echo "Uso: $0 [comando]"
            echo ""
            echo "Comandos disponíveis:"
            echo "  start    - Iniciar aplicação (padrão)"
            echo "  stop     - Parar aplicação"
            echo "  restart  - Reiniciar aplicação"
            echo "  status   - Mostrar status"
            echo "  logs     - Mostrar logs em tempo real"
            echo "  update   - Atualizar e reiniciar"
            echo "  clean    - Remover tudo (containers, imagens, volumes)"
            echo "  help     - Mostrar esta ajuda"
            ;;
            
        *)
            print_error "Comando desconhecido: $1"
            print_info "Use '$0 help' para ver os comandos disponíveis"
            exit 1
            ;;
    esac
}

# Executar função principal
main "$@" 