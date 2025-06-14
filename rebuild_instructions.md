# Instruções para Aplicar as Correções

## 1. Parar os containers atuais
```bash
cd ~/web_huawei
docker-compose down
```

## 2. Fazer backup dos logs (opcional)
```bash
cp -r logs logs_backup_$(date +%Y%m%d_%H%M%S)
```

## 3. Rebuild do container da aplicação
```bash
docker-compose build --no-cache app
```

## 4. Iniciar todos os serviços
```bash
docker-compose up -d
```

## 5. Verificar status dos containers
```bash
docker-compose ps
```

## 6. Monitorar os logs da aplicação
```bash
docker-compose logs -f app
```

## 7. Testar a aplicação
Acesse: http://200.71.84.52:5000

**Credenciais:**
- Usuário: AvanceTelecom
- Senha: Av4nc3T3l3com@#$

## O que foi corrigido:
- ✅ Erro de geração de URLs nos templates
- ✅ Endpoint 'terminal.terminal' agora funciona corretamente
- ✅ Todas as rotas dos blueprints estão registradas
- ✅ Templates renderizam sem erros

## Se ainda houver problemas:
```bash
# Ver logs detalhados
docker-compose logs app --tail 100

# Reiniciar apenas a aplicação
docker-compose restart app

# Ver status de saúde
docker-compose exec app python -c "
import requests
try:
    r = requests.get('http://localhost:5000/health')
    print(f'Health check: {r.status_code} - {r.json()}')
except Exception as e:
    print(f'Erro: {e}')
" 