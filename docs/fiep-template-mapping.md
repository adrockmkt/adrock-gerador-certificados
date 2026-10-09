# Mapeamento do certificado FIEP GA4/GTM

Arquivo recebido: `modelo-certificado.pdf`, uma página, sem senha, com área do nome em branco. O PDF enviado mede 100 × 71 pt, proporção próxima à de A4 horizontal. O app agora guarda o original e gera uma cópia de trabalho em A4 horizontal (841,89 × 595,28 pt).

## Campo dinâmico proposto

| Propriedade | Valor |
| --- | --- |
| Campo | `nome_completo` |
| Posição X | 150 pt |
| Posição Y (centro das bases) | 307 pt |
| Largura | 542 pt |
| Altura da área | 75 pt |
| Máximo de linhas | 2 |
| Fonte | Poppins Semibold |
| Tamanho inicial | 55 pt |
| Tamanho mínimo | 22 pt |
| Cor | `#FF0000` |
| Alinhamento | Centro |

O nome é formado por `Nome` + espaço + `Sobrenome` do CSV. O sistema tenta uma linha com redução precisa da fonte e usa duas linhas quando isso preserva a legibilidade. A prévia com “Marina Dias” e um nome longo foi gerada em `output/pdf/`. Esses valores devem ser conferidos no editor após o envio da versão final do PDF. A fonte pode ser trocada por Montserrat ou Lato; Avenir Next requer licença própria para instalação e incorporação.

## Pendências do PDF original

- O texto impresso contém “entro o período de” e “formtato online”. Corrigir na arte de origem antes da emissão final.
- Para impressão, recomenda-se exportar diretamente em A4 horizontal com os elementos rasterizados em resolução adequada. A ampliação automática preserva o arquivo original, mas não melhora imagens de baixa resolução.
