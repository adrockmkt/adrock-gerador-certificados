# Plano de implementação sequencial

Cada etapa deve terminar com teste local, revisão do diff e registro de riscos. O próximo componente só começa após a etapa anterior estar verificável. Commits, push e deploy dependem das autorizações aplicáveis.

| Etapa | Responsabilidade e arquivos previstos | Dependência | Critério de conclusão e testes |
| --- | --- | --- | --- |
| 1. Base e login | `app/__init__.py`, `app/auth/`, `app/models.py`, `app/templates/auth/`, configuração e testes | Especificação | Login, logout, sessão expirada, CSRF, senha com hash, limitação de tentativas e rotas privadas verificados com testes de integração. |
| 2. Clientes e eventos | `app/clients/`, `app/events/`, modelos e testes | 1 | CRUD necessário, relação cliente-evento e validação de campos em testes. |
| 3. Templates PDF | `app/templates_pdf/`, armazenamento privado e testes | 2 | Upload, leitura segura, uma página, associação e reutilização testados; PDF inválido recusado. |
| 4. Editor de campos | JavaScript/PDF.js, rotas de configuração e testes | 3 | Coordenadas em pontos preservadas sob zoom e redimensionamento; campos reposicionados corretamente. |
| 5. Fontes e prévia | Catálogo de fontes, serviço PDF e testes | 4 | Prévia PDF com acentos, variantes, alinhamento e nomes extensos revisada em amostras reais. |
| 6. Importação CSV | `app/imports/`, modelos e testes | 2 e contrato de campos | Mapeamento, revisão, duplicidades, UTF-8 e erros testados antes de confirmar. |
| 7. Emissão e downloads | `app/certificates/`, serviço de lote e testes | 5 e 6 | PDFs individuais, ZIP íntegro, acesso privado, erros individuais e prevenção de sobrescrita testados. |
| 8. Prontidão de produção | Configuração de produção e documentação operacional | 7 | Review, testes, backup/restore, monitoramento e rollback aprovados antes de alteração da VPS. |

## Primeiro arquivo real solicitado ao responsável

Na etapa 3, solicitar o PDF FIEP original, de uma página e sem senha. Na etapa 4, o administrador verá a página e posicionará o campo `nome_completo` sobre a área destinada ao nome, ajustando largura e alinhamento. A etapa 5 produzirá uma prévia real para conferência antes da emissão.

## Progresso local

- Etapas 1 a 7 implementadas e verificadas com 51 testes automatizados. O editor e a prévia foram conferidos com o PDF FIEP real, incluindo um nome extenso. A planilha modelo com `Nome` e `Sobrenome` e o arquivo de referência do Illustrator estão disponíveis por download autenticado.
- A posição e a tipografia de cada novo template ainda devem ser conferidas pelo administrador na prévia antes de gerar o lote.
- A etapa 8 foi iniciada na VPS: serviço, NGINX, HTTPS, login e downloads privados foram verificados pelo domínio. O backup local diário foi restaurado em pasta temporária e o SQLite passou em `PRAGMA integrity_check`. Ainda faltam cópia externa, medição de lotes com dados reais e política de retenção aprovada.
