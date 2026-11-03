# Fontes do corpus (frente K)

Ingerido em 2026-11-03 com `python -m app.ingest`; as páginas que vinham vazias no HTML estático foram renderizadas no Chromium por `python scripts/ingest_render.py` (só elas; os trechos já existentes mantêm o id); host permitido: site.getnet.com.br.

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

Observação: Get Clássica e Get Smart não têm página própria com slug no site (site.getnet.com.br/get-smart/ redireciona para uma imagem PNG); estão cobertas por todas-as-maquininhas e duvidas/get-smart. Get Conta = /conta-digital/ (/get-conta/ dá 404).
