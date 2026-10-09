# Especificação do MVP

## Objetivo

Permitir que um administrador da Ad Rock produza certificados PDF personalizados para eventos de diferentes clientes, começando pelo curso FIEP de GA4 e GTM.

## Fluxo

1. O administrador entra com login e senha.
2. Cadastra cliente e evento.
3. Envia um PDF de uma página ou seleciona um template existente.
4. Configura visualmente campos `nome`, `sobrenome` e `nome_completo`, incluindo posição, largura, fonte, variante, tamanho, cor, alinhamento e redução automática.
5. Importa um CSV UTF-8, mapeia nome e sobrenome, revisa erros e confirma os participantes.
6. Gera e confere uma prévia PDF real.
7. Confirma um lote e baixa PDFs individuais ou um ZIP.

## Invariantes

- O PDF original permanece preservado; a emissão usa uma versão imutável da configuração.
- Coordenadas persistidas são pontos da página PDF, independentes do zoom.
- Prévia e emissão usam o mesmo mecanismo de geração.
- Certificados e dados pessoais não são acessíveis por URLs públicas ou por `static/`.
- Duplicidades de nomes são sinalizadas, não descartadas automaticamente.
- Falhas por participante são registradas e não sobrescrevem outros certificados.
- Apenas um administrador operacional é necessário no MVP; todas as rotas sensíveis exigem autenticação.
- A exclusão de um evento remove suas importações, participantes, lotes e certificados, inclusive CSV pendente, PDFs e ZIPs gerados. A exclusão de um cliente aplica a mesma regra a todos os seus eventos. Templates PDF são globais e permanecem disponíveis para reutilização.

## Restrições

- PDFs de uma página no MVP.
- Fontes incluídas no MVP: Helvetica Regular, Montserrat, Lato e Poppins (estas três em Regular e Semibold). Avenir Next exige uma licença específica para disponibilização no servidor.
- CSV manual; sem integração direta com Google Sheets.
- Sem envio de e-mail, QR Code, assinatura digital, LMS, cobrança, SaaS ou acesso público a certificados.
- Sem fila ou worker antes de medição e aprovação.
- O deploy na DigitalOcean é uma etapa separada, depois da validação local.

## Decisões pendentes de dados reais

- O PDF FIEP será necessário para validar posição, rotação, fontes e aparência final.
- Os limites de upload e de participantes por lote serão fixados após medição com arquivos representativos.
- Retenção e exclusão de dados pessoais dependem da política aprovada pela Ad Rock e pelo cliente.

