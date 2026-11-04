# Fontes do corpus (frente K)

Ingerido em 2026-11-03 com `python -m app.ingest`; as páginas que vinham vazias no HTML estático foram renderizadas no Chromium por `python scripts/ingest_render.py` (só elas; os trechos já existentes mantêm o id); host permitido: site.getnet.com.br.

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
| suporte/get-ajuda | https://site.getnet.com.br/get-ajuda/ | 0 (renderizada, é só índice de títulos de perguntas sem resposta: fora do corpus) |
| suporte/antecipacao | https://site.getnet.com.br/get-ajuda-reserva-financeira/antecipacao-reserva-financeira/ | sup-antecipacao-01 … sup-antecipacao-04 (4) |
| suporte/reserva-financeira | https://site.getnet.com.br/get-ajuda-reserva-financeira/ | 0 (renderizada, o texto já está em suporte/antecipacao) |
| suporte/manual-maquinas | https://site.getnet.com.br/boas-vindas/manual-maquinas/ | sup-manual-maquinas-01 … sup-manual-maquinas-01 (1) |

Observação: Get Clássica e Get Smart não têm página própria com slug no site (site.getnet.com.br/get-smart/ redireciona para uma imagem PNG); estão cobertas por todas-as-maquininhas e duvidas/get-smart. Get Conta = /conta-digital/ (/get-conta/ dá 404). Antecipação de recebíveis também não tem página de produto: /antecipacao/ redireciona (301) para a FAQ da Reserva Financeira, que é a URL do slug `antecipacao`, e /antecipacao-de-recebiveis/, /antecipacao-de-vendas/ e /antecipacao-automatica/ dão 404 (conferido em 04/11/2026); sobre antecipação de vendas, o que a busca no site achou são artigos de ajuda em /get-ajuda-antecipacao-de-venda/ (como antecipar pelo app, como habilitar a automática pelo portal) e posts de blog, sem o valor da taxa, nenhum deles no corpus.
