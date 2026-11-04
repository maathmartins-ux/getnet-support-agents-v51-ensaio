# Fontes do corpus (frente K)

Produtos e suporte ingeridos em 2026-11-03 com `python -m app.ingest`; as páginas que vinham vazias no HTML estático foram renderizadas no Chromium por `python scripts/ingest_render.py` (só elas; os trechos já existentes mantêm o id); host permitido: site.getnet.com.br.

Quebra de linha entre os blocos da página (cada `<p>`/`<li>` numa linha) restaurada numa 2ª coleta no mesmo dia com o chunker novo: só entrou o trecho cujo texto é idêntico ao anterior a menos do espaço em branco (189 de 201; 12 sem mudança; 0 com conteúdo diferente); os 10 trechos novos da 2ª coleta ficaram de fora, para o gold valer sem novo rótulo (as 81 perguntas do gold de busca resolvem para os mesmos trechos). Os vetores do e5 e as notas do cross-encoder saem idênticos (os tokenizadores tratam a quebra como espaço); quem ganha é o redator, que lê uma lista em blocos (faixa de faturamento → maquininha isenta) linha a linha.

| grupo/slug | URL | trechos (ids) |
|---|---|---|
| produtos/todas-as-maquininhas | https://site.getnet.com.br/todas-as-maquininhas/ | prod-todas-as-maquininhas-01 … prod-todas-as-maquininhas-09 (9) |
| produtos/ofertas-maquininha | https://site.getnet.com.br/ofertas-maquininha-de-cartao-getnet-2/ | prod-ofertas-maquininha-01 … prod-ofertas-maquininha-15 (15; 02 em diante renderizados) |
| produtos/pix | https://site.getnet.com.br/pix/ | prod-pix-01 … prod-pix-04 (4) |
| produtos/get-conta | https://site.getnet.com.br/conta-digital/ | prod-get-conta-01 … prod-get-conta-02 (2) |
| produtos/crediario | https://site.getnet.com.br/crediario/ | prod-crediario-01 … prod-crediario-11 (11) |
| produtos/link-de-pagamento | https://site.getnet.com.br/link-de-pagamento/ | prod-link-de-pagamento-01 … prod-link-de-pagamento-04 (4) |
| produtos/pagamentos-pelo-whatsapp | https://site.getnet.com.br/pagamentos-pelo-whatsapp/ | prod-pagamentos-pelo-whatsapp-01 … -08 (8, renderizados) |
| produtos/get-tap | https://site.getnet.com.br/get-tap/ | prod-get-tap-01 … prod-get-tap-07 (6) |
| produtos/taxas | https://site.getnet.com.br/taxas/ | prod-taxas-01 … prod-taxas-02 (2; 02 renderizado) |
| suporte/duvidas | https://site.getnet.com.br/duvidas/ | sup-duvidas-01 … sup-duvidas-118 (118) |
| suporte/duvidas-get-smart | https://site.getnet.com.br/duvidas/get-smart/ | sup-duvidas-get-smart-01 … sup-duvidas-get-smart-17 (17) |
| suporte/antecipacao | https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/ | sup-antecipacao-01 … sup-antecipacao-04 (4) |
| suporte/manual-maquinas | https://site.getnet.com.br/boas-vindas/manual-maquinas/ | sup-manual-maquinas-01 … sup-manual-maquinas-01 (1) |

Os 2 índices da central de ajuda que davam 0 trechos (`suporte/get-ajuda` = /get-ajuda/ e `suporte/reserva-financeira` =
/get-ajuda-reserva-financeira/, arquivos de 0 byte) saíram em 04/11/2026: renderizados, são só títulos e links montados
por JavaScript. O texto deles são os artigos do grupo `ajuda`, abaixo.

## Central de ajuda (grupo `ajuda`, prefixo `aj`)

Ingerida em 2026-11-04 com `python scripts/ingest_render.py --discover --group ajuda`: o índice `follow.from`
(/get-ajuda/) e as 22 categorias (/get-ajuda-<categoria>/, montadas por JavaScript) são renderizados só para achar os
links; cada artigo é lido no HTML estático (é onde está o texto), com pausa de 1 s entre pedidos (125 pedidos, ~6 min).
**78 artigos, 239 trechos, 100.860 caracteres** (o corpus foi de 201 trechos em 13 páginas para 440 em 91). Ficaram de
fora: os 22 índices de categoria (sem texto próprio), /get-ajuda-maquininha/adquirindo-nossos-produtos-e-servicos/
(redireciona para /todas-as-maquininhas/, já em `produtos`), a 2ª cópia do artigo da recarga de celular (o mesmo texto
em 2 categorias; `rel=canonical`) e o artigo da antecipação da Reserva Financeira, que já é `suporte/antecipacao`.
O h1 do artigo (no `<header>` do banner) entra no texto: os 22 erros da maquininha têm quase o mesmo passo a passo e só
o título ("Erro ADQ 4-91: erro na aprovação da venda") separa um do outro. Artigo curto vira 1 trecho inteiro (só o
`erro-s-2074`, 291 caracteres); as 3 linhas de botão que a regra de repetição não pegava ("Precisa de mais
informações?", "ACESSAR · Fale já · Vamos começar", "Fale já · Vamos começar", em 5 artigos) estão em `chrome` do
grupo. Os trechos de produtos e suporte não mudaram (ids e texto iguais). No índice, o dedupe por quase-cópia junta 13
pares (eram 8): 4 erros com o mesmo passo a passo longo (ADQ 1-33 → 1-21, 1-50 → 4-30, 3-30-02 → 1-21, 4-23 → 4-27) e
`sup-duvidas-43` → `aj-o-que-e-a-get-conta-02` (a FAQ cortava a resposta de "Como abrir uma Get Conta?"; o artigo a tem).

| categoria | artigos | trechos | slugs (trechos) |
|---|---|---|---|
| `/get-ajuda-antecipacao-de-venda/` | 3 | 6 | `como-antecipar-sua-vendas-pelo-app` (2); `como-habilitar-antecipacao-automatica-pelo-portal` (2); `como-habilitar-antecipacao-automatica-pelo-app` (2) |
| `/get-ajuda-cadastro/` | 4 | 15 | `como-trocar-o-domicilio-bancario` (5); `como-atualizar-seus-dados-cadastrais-no-aplicativo-getnet-brasil` (3); `como-finalizar-seu-cadastro-no-aplicativo-getnet-brasil-e-comecar-a-aceitar-pagamentos` (4); `como-redefinir-a-senha-aplicativo` (3) |
| `/get-ajuda-cancelamento/` | 2 | 2 | `como-cancelar-produtos-e-servicos` (1); `como-cancelar-a-parceria` (1) |
| `/get-ajuda-chargeback/` | 4 | 46 | `o-que-e-chargeback` (12); `como-estornar-uma-venda-na-maquininha-getnet` (4); `como-estornar-uma-venda-pelo-aplicativo-getnet-brasil` (5); `sobre-o-chargeback` (25) |
| `/get-ajuda-conciliador-essencial/` | 1 | 7 | `sobre-o-conciliador-essencial` (7) |
| `/get-ajuda-configuracoes/` | 4 | 8 | `como-configurar-o-wi-fi-na-sua-maquininha-getnet` (3); `como-consultar-minhas-vendas` (2); `funcionalidades-portal-minha-conta-e-app-getnet-brasil` (2); `configuracoes-da-sua-maquininha` (1) |
| `/get-ajuda-conversor-de-moedas/` | 1 | 5 | `sobre-o-conversor-de-moedas` (5) |
| `/get-ajuda-ecommerce/` | 1 | 4 | `plugins-digitais-que-a-getnet-trabalha` (4) |
| `/get-ajuda-erros-maquininha/` | 22 | 23 | `erro-adq-4-83` (1); `erro-adq-4-91` (1); `erro-adq-1-50` (1); `erro-adq-4-30` (1); `erro-adq-4-23` (1); `erro-adq-4-27` (1); `erro-idl-1-04` (1); `erro-idl-1-36` (1); `erro-s-2074` (1); `erro-adq-1-02` (1); `erro-adq-1-21` (1); `erro-adq-3-30` (2); `erro-adq-1-33` (1); `erro-adq-1-07` (1); `erro-idl-1-08` (1); `erro-adq-1-19` (1); `erro-adq-1-06` (1); `erro-adq-1-87` (1); `erro-nfc` (1); `erro-adq-1-18` (1); `erro-adq-1-84` (1); `erro-adq-1-85` (1) |
| `/get-ajuda-gestao-de-vendas/` | 8 | 17 | `como-acessar-as-minhas-vendas-realizadas` (1); `como-consultar-os-status-das-minhas-vendas` (2); `quais-possiveis-status-das-minhas-vendas` (4); `como-cancelar-minhas-vendas` (3); `como-exportar-minhas-vendas-pix` (2); `onde-consultar-uma-venda-cancelada` (2); `entenda-o-que-e-venda-autorizada-aprovada-e-desfeita` (1); `como-emitir-carta-status` (2) |
| `/get-ajuda-get-conta/` | 5 | 12 | `o-que-e-a-get-conta` (4); `como-acesso-a-minha-get-conta` (3); `como-realizo-uma-transferencia-e-quais-os-limites-diarios` (2); `como-cancelar-a-minha-get-conta` (1); `o-que-e-tarifa-de-inatividade` (2) |
| `/get-ajuda-get-tap/` | 3 | 12 | `o-que-e-o-get-tap-e-como-funciona` (3); `como-utilizar-o-get-tap` (2); `como-habilitar-e-vender-com-pix-no-get-tap` (7) |
| `/get-ajuda-imposto-de-renda/` | 1 | 4 | `o-que-e-dirf` (4) |
| `/get-ajuda-maquininha/` | 6 | 17 | `como-fazer-uma-venda-na-maquininha-getnet` (4); `como-pedir-uma-maquininha-adicional` (3); `solucoes-get-smart` (3); `como-acessa-o-manual-da-sua-maquininha-getnet` (1); `simulador-calculadora-de-vendas` (4); `como-solicitar-a-manutencao-da-maquininha-getnet` (2) |
| `/get-ajuda-pix/` | 5 | 11 | `como-habilitar-o-recebimento-de-vendas-via-pix-no-aplicativo-getnet-brasil` (2); `como-fazer-uma-venda-com-pix-na-maquininha` (1); `como-utilizo-o-pix-por-biometria` (4); `como-habilitar-pix-pelo-portal` (1); `como-desabilitar-o-recebimento-de-vendas-via-pix-no-aplicativo-getnet-brasil` (3) |
| `/get-ajuda-rastreamento/` | 1 | 1 | `como-acompanhar-entrega-get-mini` (1) |
| `/get-ajuda-recarga-de-celular-pre-desligamento/` | 1 | 7 | `sobre-o-desligamento-da-recarga-de-celular` (7) |
| `/get-ajuda-receba-ja/` | 1 | 11 | `plano-de-recebimento-reduzido` (11) |
| `/get-ajuda-reserva-financeira/` | 1 | 4 | `reserva-financeira` (4) |
| `/get-ajuda-taxas/` | 1 | 5 | `taxas-por-transacao` (5) |
| `/get-ajuda-voucher/` | 2 | 18 | `como-habilitar-vale-refeicao-va-e-vale-alimentacao-vr-no-aplicativo-getnet-brasil` (7); `o-que-e-o-pat` (11) |
| `/get-ajuda-whatsapp-business/` | 1 | 4 | `descontinuacao-whatsapp-business` (4) |

Observação: Get Clássica e Get Smart não têm página própria com slug no site (site.getnet.com.br/get-smart/ redireciona para uma imagem PNG); estão cobertas por todas-as-maquininhas e duvidas/get-smart. Get Conta = /conta-digital/ (/get-conta/ dá 404). Antecipação de recebíveis também não tem página de produto: /antecipacao/ redireciona (301) para a FAQ da Reserva Financeira, que é a URL do slug `antecipacao`, e /antecipacao-de-recebiveis/, /antecipacao-de-vendas/ e /antecipacao-automatica/ dão 404 (conferido em 04/11/2026); sobre antecipação de vendas, o que a busca no site achou são artigos de ajuda em /get-ajuda-antecipacao-de-venda/ (como antecipar pelo app, como habilitar a automática pelo portal e pelo app), que desde 04/11/2026 estão no grupo `ajuda` com o passo a passo, o mínimo de R$ 50,00 e o prazo de até 48 h da habilitação; o valor da taxa de antecipação continua sem fonte no site (a FAQ diz que a automática é avaliada contrato a contrato).
