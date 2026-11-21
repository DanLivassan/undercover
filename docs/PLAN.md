# Plano de implementação do piloto

## Objetivo e limites

Entregar o piloto descrito em `docs/SPEC.md`: uma fila de sinistros, o UnderCover Agent capaz de aprovar, recusar ou encaminhar cada caso, e um dashboard para acompanhar o trabalho e autorizar pagamentos acima de US$ 1.000.

O ponto de partida é o esqueleto atual: health check em FastAPI, agente com uma ferramenta de saúde e uma tela React. A carga inicial terá somente os 25 sinistros de `data/claims.json`, de CLM-1001 a CLM-1025. Os registros relacionados virão dos arquivos explicitamente necessários em `data/`.

O agente usará as condições completas de `data/policy_wording.md`. O manual de sinistros, `data/knowledge.json`, `data/security/`, os casos reservados e os gabaritos de `data/evals/` ficam fora desta implementação. Não haverá autenticação, pagamentos reais, mensagens ao cliente, recursos AWS, execução distribuída ou funcionalidades de briefs futuros. Os testes usarão dados sintéticos e um modelo simulado, sem chamadas pagas e sem consultar gabaritos.

## Decisões de arquitetura

- Manter FastAPI, SQLite, React/Vite/TypeScript e LangChain `create_agent` com OpenRouter. Usar `sqlite3` da biblioteca padrão, sem acrescentar um ORM para este piloto.
- Persistir sinistros, decisões, autorizações, pagamentos simulados e eventos em SQLite. Importar os dados uma única vez por banco novo, sem sobrescrever trabalho existente ao reiniciar. Usar bancos temporários independentes nos testes.
- Representar dinheiro com centavos inteiros no banco e `Decimal` na validação da API. Não calcular valores monetários com ponto flutuante. A API receberá e devolverá valores em dólares com precisão de centavos.
- Separar a decisão do agente, o estado da fila e o pagamento. `approve`, `decline` e `refer` são decisões; `waiting`, `in_progress`, `waiting_for_sign_off` e `decided` são estados de trabalho. Pagamento terá seu próprio registro.
- Converter o estado inicial `open` em `waiting`. Preservar a ordem dos registros de `claims.json` como ordem da fila, com um índice explícito.
- Reservar o sinistro atomicamente antes de executá-lo. Uma segunda execução não poderá assumir um caso em andamento ou já concluído.
- O agente obterá instruções e dados exclusivamente pela API HTTP. Não importará módulos de armazenamento do backend nem abrirá arquivos de negócio. As instruções terão uma única fonte no backend e serão exibidas sem edição no dashboard.
- Persistir eventos de início, chamadas e resultados de ferramentas, decisão, autorização, pagamento e falha. Exibir essas ações observáveis, sem solicitar ou armazenar raciocínio privado do modelo.
- Atualizar fila e eventos por polling simples no dashboard. A execução do agente será iniciada pela linha de comando neste piloto.
- Manter a interface em inglês americano, com moeda USD e a identidade de `docs/BRAND.md`. O plano está em português para revisão pelo estudante.

## Fase 1 — Dados e persistência

Criar a base SQLite e a carga inicial explícita. Esta fase estabelece os dados e os estados em que as próximas fases vão trabalhar.

Implementar um módulo de armazenamento no backend, modelos de domínio e inicialização pelo ciclo de vida do FastAPI. Carregar os sinistros, clientes, apólices, planos, atendentes, limite de autorização de `company.json` e condições da apólice. Não expor regras internas do manual presentes em configurações da empresa como regras de decisão do agente. Guardar documentos textuais e itens sem perder informações do arquivo de origem.

Critérios de sucesso:

- [x] Um banco vazio recebe exatamente 25 sinistros em `waiting`, na ordem CLM-1001 a CLM-1025, e os relacionamentos necessários para consultar cliente, histórico, apólice e plano.
- [x] Testes verificam a preservação de narrativa, itens e documentos, incluindo caracteres especiais e valores em centavos.
- [x] Inicializar duas vezes ou reiniciar o backend não duplica registros nem apaga decisões, pagamentos ou eventos existentes.
- [x] Testes usam bancos temporários e não alteram o banco de desenvolvimento ou os JSONs originais.
- [x] Um teste observa os caminhos lidos pela carga inicial e comprova que somente os arquivos autorizados são abertos; nenhum acesso a `evals/`, `security/`, manual ou conhecimento adicional.
- [x] `uv run pytest -q backend/tests` passa para os cenários desta fase; `docs/STATUS.md` documenta a localização do banco e a inicialização.

## Fase 2 — API e regras de decisão, autorização e pagamento

Implementar operações pequenas com contratos tipados. As regras que impedem pagamentos indevidos ficam no backend, para valerem mesmo quando uma ferramenta do agente é chamada incorretamente.

Contrato previsto, com todos os campos de entrada obrigatórios:

| Operação | Finalidade e resposta principal |
|---|---|
| `GET /api/health` | Manter `200 {"status":"ok"}`. |
| `GET /api/claims` | Listar a fila em ordem, com identificadores, cliente, tipo, valor, estado e resumo da decisão. |
| `GET /api/claims/{claim_id}` | Consultar todos os dados do sinistro, decisão, autorização e pagamento. |
| `GET /api/claims/{claim_id}/context` | Consultar cliente e histórico, apólice, plano e adicionais aplicáveis. |
| `GET /api/policy-wording` | Consultar as condições completas e sua versão. |
| `GET /api/agent/instructions` | Consultar as instruções que o agente realmente usa. |
| `GET /api/handlers` | Listar atendentes disponíveis para autorização. |
| `GET /api/claims/{claim_id}/events` | Consultar eventos em ordem, com horário, tipo e conteúdo. |
| `POST /api/claims/{claim_id}/start` | Receber `thread_id`, reservar o caso e registrar o início. |
| `POST /api/claims/{claim_id}/events` | Receber `thread_id`, tipo e conteúdo de um evento da execução. |
| `POST /api/claims/{claim_id}/decision` | Receber `thread_id`, resultado, valor, cálculo, justificativa e seção da apólice. |
| `POST /api/claims/{claim_id}/sign-off` | Receber `handler_id` e autorizar a decisão pendente. |
| `POST /api/claims/{claim_id}/pay` | Receber o valor e registrar um pagamento simulado separado da decisão. |
| `POST /api/claims/{claim_id}/failure` | Receber `thread_id` e descrição da falha; registrar o erro e devolver uma execução não concluída à fila. |

Usar `404` para registros inexistentes, `422` para entradas inválidas e `409` para conflitos de estado. Cada operação terá `operation_id` único e docstring de uma linha. Consultas terão formatos fixos, sem filtros ou parâmetros opcionais neste piloto.

Aprovar acima do limite leva a `waiting_for_sign_off`, sem pagamento. Um atendente válido autoriza essa decisão e o pagamento continua sendo uma operação separada. O dashboard executará essas duas operações em sequência, deixando uma falha de pagamento visível e permitindo tentar novamente sem nova autorização. Aprovações até o limite ficam em andamento até o pagamento; recusas e encaminhamentos concluem o trabalho em `decided`, preservando a diferença entre esses resultados. Encaminhar encerra a análise automática e deixa a necessidade de revisão explícita.

Critérios de sucesso:

- [x] TestClient verifica `200` nos endpoints de leitura, os 25 casos na ordem correta e `404` para um identificador inexistente.
- [x] A reserva só aceita `waiting`; duas tentativas concorrentes resultam em uma reserva e um conflito. Escritas da execução exigem o `thread_id` ativo.
- [x] Testes verificam as transições para aprovação, recusa e encaminhamento, incluindo resultado, cálculo, justificativa de duas ou três frases e referência à seção da apólice.
- [x] Uma aprovação de US$ 1.000 permite pagamento sem autorização; US$ 1.000,01 fica em `waiting_for_sign_off` e a chamada direta a `/pay` retorna `409`, sem criar pagamento.
- [x] Após autorização por atendente válido, o pagamento do valor aprovado é aceito e o caso fica `decided`. Atendente inexistente ou sem permissão não autoriza o pagamento.
- [x] Pagamentos negativos, com frações de centavo, diferentes do valor aprovado, anteriores à decisão ou para decisões recusadas/encaminhadas são rejeitados. Repetir a chamada não cria um segundo pagamento.
- [x] Alterar uma decisão concluída ou autorizada é rejeitado, impedindo que a autorização seja reutilizada para outro valor.
- [x] Eventos, autorização e pagamento persistem após reiniciar o backend. Uma falha de execução preserva os eventos e não apaga uma decisão ou um pagamento já concluído.
- [x] O OpenAPI confirma `operation_id` único, entradas obrigatórias e ausência de parâmetros opcionais em todas as operações.
- [x] Os testes do backend passam e `docs/STATUS.md` descreve estados, operações e o bloqueio financeiro.

## Fase 3 — Agente de análise de sinistros

Substituir o agente de demonstração por um agente que lê o caso, busca o contexto e as condições, decide e registra o resultado pelas ferramentas HTTP. Preservar `run(claim_id, thread_id)` e a injeção de modelo simulado para testes.

As instruções explicarão a ordem de análise: cobertura e datas, documentos, exclusões, limites e adicionais, reembolsos de terceiros, franquia e teto do benefício. O resultado terá `approve`, `decline` ou `refer`, valor em USD, memória do cálculo, duas ou três frases de justificativa e a seção relevante da apólice. Informações ausentes ou situações que a apólice não resolve devem gerar encaminhamento, sem inventar regras do manual.

Usar `openai/gpt-6-luna` com esforço baixo como padrão e respeitar `MODEL_NAME`, inclusive `openrouter/free`. Buscar as instruções na API antes de criar o agente. Fornecer somente ferramentas necessárias à análise e ao pagamento simulado, sem ferramenta de autorização por atendente. Registrar chamadas, resultados e erros durante a execução. Uma aprovação acima do limite termina com a decisão pendente de autorização; não tenta contornar o bloqueio.

Critérios de sucesso:

- [x] Um modelo simulado percorre leitura do sinistro, contexto, condições, decisão e pagamento, deixando eventos ordenados no backend.
- [x] Casos sintéticos cobrem aprovação, recusa, encaminhamento por documento ausente e aprovação acima do limite, sem usar gabaritos.
- [x] As instruções incluem cálculo na ordem da seção 10, limites por item e benefício, adicionais e referência às condições; não incluem regras exclusivas do manual.
- [x] Um teste comprova que a mesma versão de instruções retornada pela API é passada a `create_agent`.
- [x] Testes confirmam modelo padrão, esforço baixo e uso de `MODEL_NAME` quando definido. Todos os testes rodam sem chave OpenRouter e sem tráfego para um provedor de modelos.
- [x] Não existe ferramenta de autorização no conjunto do agente; tentar pagar acima do limite sem autorização recebe a recusa do backend e não cria pagamento.
- [x] Falha HTTP ou falha do modelo fica visível nos eventos, encerra a execução com erro identificável e não deixa um caso sem decisão preso em andamento.
- [x] Os testes do agente passam e `docs/STATUS.md` descreve a configuração e o fluxo de análise.

## Fase 4 — Execução individual e processamento da fila

Adicionar `agent/__main__.py` para executar um caso ou a fila inteira de forma sequencial. Consultar os casos pela API, selecionar somente os que estão esperando e manter a ordem da fila. Gerar um `thread_id` por tentativa e usar a mesma função `run` nos dois modos. Essa abordagem atende o piloto sem introduzir dispatcher ou execução em paralelo.

Critérios de sucesso:

- [x] `uv run -m agent CLM-1001` inicia somente esse caso e imprime identificador, resultado, valor e estado final; testes do CLI substituem o modelo por um stub.
- [x] `uv run -m agent` processa cada caso em `waiting` na ordem devolvida pela API, sem executar casos em andamento, pendentes de autorização ou concluídos.
- [x] Os testes mostram que cada tentativa usa um `thread_id` distinto e que executar novamente a fila não repete decisões ou pagamentos concluídos.
- [x] Identificador inexistente e backend indisponível produzem mensagem útil e código de saída diferente de zero.
- [x] Uma falha em um caso é registrada; os demais casos da fila continuam. O resumo identifica sucessos e falhas e o processo termina com código não zero se houve falha.
- [x] Duas execuções não trabalham simultaneamente no mesmo caso, respeitando a reserva da fase 2.
- [x] `docs/STATUS.md` inclui `uv run -m agent` e `uv run -m agent CLM-1001`, necessidade do backend ativo e variáveis de ambiente exigidas.

## Fase 5 — Dashboard para os atendentes

Construir a fila, o detalhe do sinistro e uma página de instruções somente para leitura. A fila mostrará os quatro estados com rótulos claros; o detalhe exibirá narrativa completa, itens, documentos, cliente e histórico, apólice e plano, decisão, cálculo, justificativa, seção da apólice e situação do pagamento.

Mostrar a atividade do agente em uma linha do tempo atualizada por polling, inclusive enquanto o caso estiver em andamento. Nos casos pendentes, permitir selecionar um atendente e autorizar o pagamento. Exibir carregamento, fila vazia, falha de rede e erro de operação com possibilidade de repetir a consulta ou operação pertinente.

Aplicar Instrument Sans e JetBrains Mono, superfícies arredondadas e cores de `docs/BRAND.md`, com contraste legível. Usar HTML semântico, foco visível e layouts que funcionem em telas menores. Não adicionar controles para editar instruções ou disparar execução do agente pelo navegador.

Critérios de sucesso:

- [x] Vitest/Testing Library verifica a fila, os quatro estados, seleção de um sinistro, dados completos e decisões de aprovação, recusa e encaminhamento.
- [x] Testes com timers controlados verificam atualização da fila e eventos por polling e cancelamento das consultas periódicas ao sair da tela.
- [x] A página de instruções mostra o texto real retornado pelo backend, sem campos editáveis.
- [x] O fluxo de autorização mostra o atendente e o valor, aguarda a resposta do backend e só apresenta pagamento concluído após sucesso de `/pay`.
- [x] Uma falha de pagamento após a autorização fica visível e permite repetir apenas o pagamento, sem duplicação.
- [x] Testes cobrem carregamento, fila vazia, indisponibilidade da API e erro na autorização. Botões ficam indisponíveis enquanto a operação estiver em curso.
- [x] Pelo Playwright MCP, conferir fila, detalhes, instruções e eventos atualizados em navegador real, em larguras de 1440 px e 390 px, sem rolagem horizontal nem erros no console.
- [x] Pelo Playwright MCP, conferir navegação por teclado, rótulos dos controles, foco e valores como `$1,250.00`; verificar cores e fontes contra `docs/BRAND.md`.
- [x] `npm run check:ts` passa, com TypeScript estrito, sem `any` e cobertura mínima de 80%; atualizar `docs/STATUS.md` com as telas disponíveis.

## Fase 6 — Integração, verificação e entrega

Consolidar os fluxos completos com backend real, SQLite temporário e modelo simulado. Os testes de integração deverão controlar o banco e a execução do agente sem depender da chave OpenRouter ou do banco de desenvolvimento.

Critérios de sucesso:

- [x] Playwright verifica um caso que sai de `waiting`, exibe eventos em `in_progress` e termina aprovado e pago, com decisão e justificativa no detalhe.
- [x] Playwright verifica aprovação acima de US$ 1.000: a API bloqueia pagamento direto antes da autorização, o dashboard mostra a pendência, um atendente autoriza e um único pagamento é registrado.
- [x] Playwright verifica recusa e encaminhamento, exibindo motivos e seção da apólice, sem pagamento ou ação de autorização.
- [x] Uma verificação integrada demonstra persistência de decisão, eventos e pagamento após reiniciar o backend no mesmo banco temporário.
- [x] `uv sync` e `npm install` na raiz completam a instalação; o hook de pre-commit está instalado. Usar Python 3.12 e Node 26 conforme a documentação.
- [x] `npm run dev` inicia backend e dashboard; `GET /api/health` retorna `200 {"status":"ok"}` e o navegador abre a fila.
- [x] `npm run check` passa integralmente: Ruff, Pyright, pytest com cobertura mínima de 80%, Prettier, ESLint, TypeScript, Vitest com cobertura mínima de 80% e Playwright.
- [x] Scripts adicionados funcionam em Windows e Linux/macOS, usando comandos `uv run` ou arquivos `.mjs`, sem dependência de sintaxe exclusiva do Bash.
- [x] `docs/STATUS.md` registra instalação, inicialização, localização do banco, CLI nos dois modos, configuração do modelo, autorização, testes e limites conhecidos do piloto.
- [x] Revisar o diff final para confirmar ausência de acesso a gabaritos, manual ou dados de etapas futuras, de segredos versionados e de recursos AWS.

## Como implementar após a revisão

Implementação autorizada e concluída nas seis fases. Os critérios acima foram verificados com testes automatizados e inspeção no navegador; veja `docs/STATUS.md` para execução e resultados.

Na implementação, executar as seis fases em ordem. Em cada fase, construir com testes, verificar os critérios, marcar somente os itens comprovados, atualizar `docs/STATUS.md` e fazer commit com o hook ativo. Corrigir falhas sem desativar regras ou reduzir cobertura. Não fazer push. Ao concluir, executar `npm run check` e informar o resultado e qualquer limitação restante.
