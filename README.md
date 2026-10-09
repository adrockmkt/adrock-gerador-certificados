# Ad Rock Certificate Generator

Painel administrativo para cadastrar clientes e eventos, mapear campos em um PDF original, importar participantes de CSV e emitir certificados individuais ou em ZIP.

A interface segue a linguagem visual **Ad Rock Console UI** do projeto organizacional `relatorios-porvir`: fundo claro, cartões brancos, bordas azul claras, detalhes laranja e logo Ad Rock.

## Estado atual

O fluxo está implementado: login, clientes e eventos, upload privado de template, editor visual, prévia PDF, importação CSV com revisão e geração de lotes. O PDF real da FIEP foi recebido e usado na conferência visual local. Há 48 testes automatizados. A aplicação está publicada em [mobiledelivery.com.br/gerador-certificados/](https://mobiledelivery.com.br/gerador-certificados/).

## Instalação local

Requer Python 3.9 ou superior e um navegador atual. No diretório do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m flask --app app init-admin
python -m flask --app app run
```

Guarde o `SECRET_KEY` da instalação fora do repositório e use o mesmo valor ao reiniciar. O `init-admin` solicita usuário e senha com pelo menos 12 caracteres. Para redefinir a senha localmente, use `python -m flask --app app reset-admin-password`; sessões anteriores são invalidadas.

O SQLite fica em `instance/certificates.sqlite3` e os arquivos privados em `instance/private` por padrão. Ambos são ignorados pelo Git. As variáveis disponíveis estão em [.env.example](.env.example).

## Uso

1. Entre com a conta administrativa e cadastre o cliente e o evento.
2. Envie o PDF original diagramado, com uma página, sem senha e sem o nome do participante impresso. Associe o template ao evento. O arquivo original é preservado.
3. Abra o editor, escolha **Nome completo** e clique em **Adicionar campo**. Arraste o campo até a área reservada ao nome. Ajuste largura, altura, máximo de linhas, fonte, tamanho, cor e alinhamento; salve a configuração. O nome completo combina `Nome` e `Sobrenome` do CSV. Nomes longos podem ser reduzidos ou quebrados em duas linhas dentro da área definida.
4. Abra **Prévia PDF** no editor e confira o resultado real. Se necessário, ajuste e salve uma nova versão. A emissão usa a versão salva mais recente no momento em que o lote é criado.
5. No evento, abra **Participantes e importação CSV**. Baixe a planilha modelo (.xlsx), preencha as colunas `Nome` e `Sobrenome` e exporte a aba `Participantes` como CSV UTF-8. Envie o CSV (com ou sem BOM), separado por vírgula ou ponto e vírgula. Escolha as colunas de nome e sobrenome, revise linhas inválidas e duplicadas e confirme a importação.
6. Abra **Gerar certificados**, confirme que conferiu a prévia e gere o lote. Baixe os PDFs individuais ou o ZIP. O resultado registra separadamente os nomes que não couberam no campo.

O limite atual é 5 MB por upload, 500 linhas de dados por CSV e 500 participantes por lote. Templates com rotação de página são recusados até que o editor suporte essa geometria. Estão disponíveis Helvetica Regular e as famílias abertas Montserrat, Lato e Poppins em Regular e Semibold. As licenças OFL ficam junto aos arquivos de fonte. O tamanho de fonte é reduzido até o mínimo configurado quando necessário.

Na página **Templates PDF**, o modelo do certificado em Illustrator (.ai) fica disponível para download como referência de design. O sistema usa o PDF enviado na emissão; o arquivo `.ai` não substitui essa etapa.

PDFs horizontais de proporção A4 exportados em tamanho muito pequeno são ampliados para A4 horizontal no arquivo de trabalho. O arquivo enviado permanece guardado e pode ser baixado pela lista de templates. Para qualidade de impressão, prefira exportar o original diretamente em A4 com imagens em boa resolução.

## Segurança e operação

Todos os documentos e dados ficam atrás de login. Há proteção CSRF, hash de senha, limitação de tentativas de login, cookie de sessão protegido e cabeçalhos de segurança. PDFs e CSVs não são servidos por `static/`. O CSV original é removido após confirmação; participantes e certificados emitidos permanecem até exclusão administrativa conforme a política de retenção que ainda será definida.

Para produção, configure `SESSION_COOKIE_SECURE=1`, HTTPS no proxy, `TRUSTED_HOSTS`, um `SECRET_KEY` persistente, permissões restritas em `instance/` ou no diretório privado e backups consistentes do banco e dos PDFs. Execute com um servidor WSGI, como Gunicorn, instalado com `pip install -e '.[production]'`. **Não use `flask run` em produção.** O app cria as tabelas iniciais automaticamente em uma instalação vazia; alterações futuras do esquema exigirão migrações versionadas. Antes do deploy, teste backup/restauração, desempenho com arquivos reais e a política de retenção. Veja [prontidão de produção](docs/production-readiness.md).

Na VPS atual, o código fica em `/home/adrock/apps/gerador-certificados`, os dados em `/var/lib/gerador-certificados` e o backup local em `/var/backups/gerador-certificados`. O NGINX encaminha somente o subcaminho do gerador ao Gunicorn em `127.0.0.1:8012`. A senha inicial do administrador foi gerada no servidor e guardada em `/root/gerador-certificados-bootstrap.txt`, com acesso exclusivo ao root. Após guardá-la em um gerenciador de senhas, remova esse arquivo. A cópia externa dos backups e a política de retenção dos certificados ainda precisam ser definidas.

Testes:

```bash
python -m unittest discover -s tests -v
```

Os documentos de governança da Ad Rock ficam no diretório organizacional `modelos_de_codigo`; são consultados e não são copiados para este projeto.
