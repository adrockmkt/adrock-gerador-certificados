# Prontidão para hospedagem DigitalOcean

Este documento prepara a implantação; nenhuma alteração foi feita na VPS.

## Configuração mínima

- Instância Linux com Python compatível, usuário de serviço sem privilégios e diretório privado fora da raiz pública do NGINX.
- Ambiente virtual com `pip install -e '.[production]'` e Gunicorn executando `app:create_app()` sob systemd. Não habilitar debug.
- NGINX como proxy HTTPS com certificado válido, limite de corpo de requisição coerente com os 5 MB do app, redirecionamento HTTP para HTTPS e acesso apenas à porta do proxy pela internet.
- Definir `SECRET_KEY` longo e persistente, `SESSION_COOKIE_SECURE=1`, `TRUSTED_HOSTS` com o domínio real, `DATABASE_URL` e `PRIVATE_STORAGE_DIR` em variáveis de ambiente protegidas. Não colocar segredos no Git, logs ou unidade systemd legível publicamente.
- SQLite é viável para instalação pequena de um administrador, desde que haja um único processo de escrita e backups consistentes. Medir tempo de geração com PDFs reais antes de escolher timeout do Gunicorn; lotes síncronos grandes podem excedê-lo. Caso aumente a concorrência, planejar PostgreSQL e processamento assíncrono em nova etapa.

## Implantação em mobiledelivery.com.br

O código fica em `/home/adrock/apps/gerador-certificados`, executado por um usuário de serviço `certgen` sem login. O SQLite e os arquivos gerados ficam em `/var/lib/gerador-certificados`, fora da raiz pública. O serviço Gunicorn escuta apenas em `127.0.0.1:8012` e o NGINX encaminha `/gerador-certificados/` com `X-Forwarded-Prefix`. Os modelos de serviço e NGINX estão em `deploy/`.

As variáveis de produção ficam em `/etc/adrock/gerador-certificados.env`, com permissão `0600` para root. Defina `SECRET_KEY`, `DATABASE_URL=sqlite:////var/lib/gerador-certificados/certificates.sqlite3`, `PRIVATE_STORAGE_DIR=/var/lib/gerador-certificados/private`, `APPLICATION_ROOT=/gerador-certificados`, `SESSION_COOKIE_SECURE=1` e `TRUSTED_HOSTS=mobiledelivery.com.br,www.mobiledelivery.com.br`. Não publique esse arquivo no Git.

Antes de recarregar o NGINX, faça cópia do vhost atual e execute `nginx -t`. Depois, confira redirecionamento, login, cookie restrito ao subcaminho, downloads privados, cabeçalhos e estado do serviço pelo domínio real.

O backup local diário usa `deploy/backup-vps.sh` com um timer systemd às 03:15. Ele interrompe brevemente o serviço para arquivar SQLite e arquivos privados no mesmo estado, grava em `/var/backups/gerador-certificados` com acesso root e conserva 14 dias. Teste a extração e `PRAGMA integrity_check` em diretório temporário. Esse backup no mesmo disco não cobre a perda da VPS; configure uma cópia externa quando o destino e a política forem definidos.

## Verificações antes de publicar

1. Gerar certificados de teste com o PDF real da FIEP, incluindo nomes curtos, longos e acentuados, e revisar visualmente PDF e ZIP.
2. Repetir `python -m unittest discover -s tests -v` no ambiente de implantação.
3. Confirmar HTTPS, login, logout, bloqueio de tentativas, CSRF, acesso negado a documentos sem sessão e cabeçalhos de segurança pelo domínio público.
4. Criar backup consistente do SQLite e do armazenamento privado no mesmo ponto lógico; restaurar ambos em ambiente isolado e abrir um certificado restaurado.
5. Definir com a Ad Rock e o cliente a retenção de participantes e certificados. O app ainda não implementa exclusão automática.
6. Configurar logs de processo sem dados pessoais, alertas de falha e espaço em disco; verificar acesso aos arquivos apenas pelo usuário de serviço.
7. Ter uma cópia anterior do código e dos dados para rollback. Uma mudança de esquema exige migração versionada e procedimento de reversão.

## Limites atuais

O sistema não foi implantado na DigitalOcean. Ainda faltam medição com PDF real, política de retenção e migrações para evoluções de esquema. O app cria somente o esquema inicial de uma instalação vazia.
