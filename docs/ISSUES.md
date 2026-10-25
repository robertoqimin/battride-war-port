# Erros, falhas e problemas reportados

Levantamento de tudo o que foi reportado até 23/10/2026, com a situação atual de cada item. "Resolvido" significa corrigido e medido nos testes feitos; não significa validado no jogo inteiro.

## Resumo

| # | Problema | Área | Situação |
|---|---|---|---|
| 1 | Estouro do buffer de comandos gráficos (~19 MiB) | Gráficos / sincronização | Resolvido |
| 2 | FPS muito baixo e variável em combate | Desempenho | Parcial: ~30 fps no combate comum, cai para ~20 com muitos inimigos |
| 3 | FPS cai ao andar e com multidões | Desempenho | Resolvido (~38 fps de média) |
| 4 | Áudio com interrupções e estalos | Áudio | Parcial: ainda quebra em combate (teste manual) |
| 5 | Brilho excessivo intermitente | Gráficos | Em aberto |
| 6 | Cores e efeitos especiais incorretos | Gráficos | Em aberto |
| 17 | Sombras incorretas | Gráficos | Resolvido na primeira missão |
| 7 | Conclusão de missões | Gameplay | Validado na primeira missão (teste manual) |
| 8 | Jogo completo não validado | Gameplay | Em aberto |
| 9 | Estabilidade prolongada | Estabilidade | Parcial (~30 min sem falhas) |
| 10 | Thread de render do jogo quase saturada | Desempenho | Em aberto (confirmado: ~20 fps com muitos inimigos) |
| 11 | Áudio depende do firmware local | Áudio | Limitação conhecida |
| 12 | Codec ATRAC não exercitado | Áudio | Não testado |
| 13 | Encerramento limpo não validado em todos os caminhos | Estabilidade | Em aberto |
| 14 | Processos de teste remanescentes contaminaram medições | Ferramentas de teste | Contornado |
| 15 | Toques curtos do `PAD_FILE` perdidos com o jogo mais rápido | Ferramentas de teste | Contornado |
| 16 | Personagem não se move pelo direcional | Ferramentas de teste | Contornado (`PORT_PAD_STICK_FILE`) |

## Detalhes

### 1. Estouro do buffer de comandos gráficos — Resolvido
- **Sintoma:** a missão inicial gerava ~19 MiB de comandos RSX e estourava as duas arenas de 4 MiB do jogo, sobrescrevendo dados do renderizador. O contorno anterior alocava 2×32 MiB extras.
- **Causa:** o `sys_lwcond` do SDK espera em polling de 1 ms e seus `signal` não fazem nada. A thread de render do jogo espera uma única vez pelo evento de frame, então nunca bloqueava e redesenhava o frame inteiro dezenas de vezes por flip (708 renderizações contra 9 flips em 15 s).
- **Correção:** `sys_lwcond` bloqueante em `stubs.cpp` (commit `3ce00f8`). O frame da missão cai para um pico de ~0,5 MiB. A expansão de buffers ficou desligada por padrão (`PORT_GCM_EXPAND_BUFFERS=1` a reativa).

### 2. FPS baixo em combate — Resolvido
- **Sintoma:** ~6 fps em combate.
- **Causas e correções (commits `75611ca` e `05af18b`):**
  - build inteiro em `-O0` → `-O2`;
  - um envio com espera na GPU por draw → comandos Vulkan em lotes, com dois slots;
  - checagens de depuração em cada escrita de memória do jogo → saem cedo quando não há nenhuma ativa;
  - `getenv` no laço do FIFO → lido uma vez só;
  - relógio de frames com espera fixa e present bloqueante → acordado pelo jogo, present sem esperar a GPU.
- **Resultado:** ~30 fps em combate (29,7 / 30,3 / 30,7).
- **Teste manual (23/10/2026):** com muitos inimigos na tela o FPS ainda cai para ~20. Ver item 10.

### 3. Queda de FPS ao andar — Resolvido
- **Sintoma:** 20–24 fps andando e em cenas com muitos inimigos (relatado no teste manual).
- **Causa:** o present da janela em modo FIFO (vsync) bloqueava a thread do FIFO até o vblank, então um frame de pouco mais de 33 ms esperava até 50 ms.
- **Correção:** modo MAILBOX quando o driver oferece (commit `22cab93`); `PS3RECOMP_VK_VSYNC=1` mantém o FIFO.
- **Resultado:** 38 fps de média e 29,4 no percentil 10 em 150 s de luta e caminhada; ~35 fps de média numa sessão de ~32 min.

### 4. Áudio com interrupções — Resolvido nos trechos testados
- **Sintoma:** cortes e estalos; o som saía em rajadas (4 blocos de som, 8 de silêncio).
- **Causa:** a tarefa de áudio do SPU, rejeitada pelo tradutor estático, rodava interpretada e preenchia só ~1/3 dos blocos a tempo. Em combate, quase todo o trabalho é o codec `flashMP3.pic`, também interpretado.
- **Correção (commit `08c0e61`):**
  - tradução da tarefa abaixo de `0x171D0` e do codec MP3 (`scripts/lift_audio_spu.py`);
  - interpretador com cache de decodificação;
  - camada de canais sem `getenv` por acesso;
  - código SPU compilado com `-msse4.1`.
- **Resultado:** zero blocos vazios na música do título e em 45 s de combate.
- **Ressalvas:** sessões longas e outras fases não foram verificadas.
- **Teste manual (23/10/2026):** o áudio ainda quebra em combate. Como coincide com as quedas de FPS, a suspeita é disputa de CPU: a thread de áudio do SPU e a thread de render do jogo ficam ambas perto de 100%.

### 5. Brilho excessivo intermitente — Em aberto
Relatado no estado inicial do projeto e não investigado. Um frame posterizado em amarelo e vermelho foi visto na entrada da missão quando ainda havia redesenho repetido (item 1). Não foi confirmado se persiste depois das correções.

### 6. Cores e efeitos especiais incorretos — Em aberto
Relatado no estado inicial do projeto; não investigado. Provavelmente envolve o backend Vulkan (blend, formatos de superfície ou constantes de fragment program).

### 17. Sombras incorretas — Resolvido na primeira missão
- **Sintoma:** os personagens não projetavam sombra, e o chão dentro do alcance do *shadow map* ficava todo escurecido; fora dele (uma região retangular com borda reta) ficava claro.
- **Causa:** o jogo desenha as silhuetas dos personagens num *shadow map* Z24S8 de 1024×1024 e o amostra na cena (unidade t3, formato DEPTH24_D8, `zfunc` LESS, filtro linear). No RSX a comparação de profundidade da textura é `profundidade armazenada OP referência`; o auxiliar do SDK fazia `referência OP profundidade armazenada`. Com a direção trocada, o resultado ficava invertido em todo pixel, e as contas do shader do jogo marcavam o chão inteiro como sombreado.
- **Correção:** `rsx_engine_bridge.c` inverte a direção do `zfunc` (LESS↔GREATER, LEQUAL↔GEQUAL) antes de traduzir o shader. `PORT_SHADOW_REVERSE=0` volta ao comportamento anterior para comparação.
- **Segunda causa (borda):** o shadow map usa o modo de repetição BORDER com cor de borda `0xFFFFFFFF` (profundidade 1,0: fora do mapa nada faz sombra). O backend Vulkan usava sempre borda preta, e tudo fora do mapa lia profundidade 0 e ficava "na sombra": na cena de abertura, o chão do holofote aparecia como uma faixa clara de bordas retas em vez de uma mancha redonda. `eng_decode_sampler` agora leva a classe da cor de borda (preto transparente, preto opaco ou branco opaco, as cores fixas do Vulkan) até `vk_eng_sampler`.
- **Verificado:** comparado com uma gravação do jogo original (YouTube `u4YixUZPH30`, a partir de 3:05): a cena do holofote fica praticamente idêntica (mancha de luz redonda e a sombra longa do personagem), e no combate da STG02 o chão fica iluminado com a sombra de cada personagem a partir dos pés. Desempenho igual. Outras missões não foram verificadas.

### 7. Conclusão de missões — Validado na primeira missão
- **Teste manual (23/10/2026):** a primeira missão (STG02) foi concluída jogando manualmente, e ao terminar o jogo foi para a seleção de missões normalmente. As demais missões não foram testadas.
- **Tentativa automatizada anterior:** numa sessão automatizada de ~30 min na STG02, foram 350 inimigos derrotados e combo máximo de 50, mas o objetivo ficou em "先へ進め" (avance) até o tempo da missão (30 min) acabar.
- **Conclusão:** o teste manual mostrou que a falha era do piloto automático, não do port.

### 8. Jogo completo — Em aberto
Só a primeira missão foi concluída; as demais não foram testadas.

### 9. Estabilidade prolongada — Parcial
Houve ~30 min de missão contínua sem travamento e sem erros no log, até o limite de tempo do script de teste. Sessões mais longas, troca de fases e carregamentos repetidos não foram testados.

### 10. Thread de render quase saturada — Em aberto
Confirmado no teste manual: com muitos inimigos o FPS cai para ~20. A ~30 fps, a thread de render do jogo fica em ~98% de CPU, então cenas mais pesadas podem cair abaixo de 30 fps. Opções:
- compilar com instruções FMA (`-mfma`, exige CPUs com AVX2/FMA, uma decisão de portabilidade);
- reduzir as barreiras e render passes por draw no Vulkan.

### 11. Áudio depende do firmware local — Limitação conhecida
A tradução do codec MP3 só é gerada se o `flashMP3.pic` local tiver o SHA-256 verificado. Sem ele, o codec fica interpretado e o combate provavelmente volta a ter cortes. Sem nenhum codec, a tarefa de áudio para (ver `README_FIRMWARE.md`).

### 12. Codec ATRAC — Não testado
O jogo não abriu o `flashATRAC.pic` nos testes. Se for usado em outras fases, roda interpretado e pode ter cortes.

### 13. Encerramento limpo — Em aberto
Execuções com limite de tempo às vezes exigem SIGKILL (já anotado no `docs/BUILD.md`).

### 14. Processos de teste remanescentes — Contornado
Um processo antigo do jogo sobreviveu ao `pkill -f` e rodou junto com o novo, contaminando duas medições. Os testes passaram a encerrar o jogo pelo PID e a confirmar que nenhum processo ficou rodando.

### 15. Toques curtos do `PAD_FILE` perdidos — Contornado
Com o jogo mais rápido, toques de 8 polls às vezes não eram registrados (o START da abertura, o ○ da escolha de dificuldade). Os scripts passaram a segurar os botões por mais tempo.

### 16. Personagem não se move pelo direcional — Contornado
Neste jogo o personagem só anda pelo analógico esquerdo, e o SDK só permite fixar o analógico desde o início (`PAD_STICK`). `PORT_PAD_STICK_FILE` (commit `1a8c94a`) permite controlar os dois analógicos por arquivo durante os testes.
