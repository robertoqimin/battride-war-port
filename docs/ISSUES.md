# Erros, falhas e problemas reportados

Levantamento de tudo o que foi reportado até 25/10/2026, com a situação atual de cada item. "Resolvido" significa corrigido e medido nos testes feitos; não significa validado no jogo inteiro.

## Resumo

| # | Problema | Área | Situação |
|---|---|---|---|
| 1 | Estouro do buffer de comandos gráficos (~19 MiB) | Gráficos / sincronização | Resolvido |
| 2 | FPS muito baixo e variável em combate | Desempenho | Resolvido no combate medido (~58 fps de média em luta, pior trecho de 5 s ~47 fps) |
| 3 | FPS cai ao andar e com multidões | Desempenho | Resolvido (MAILBOX; ver item 2 para os números atuais) |
| 4 | Áudio com interrupções e estalos | Áudio | Parcial: ainda quebra em combate (teste manual) |
| 5 | Brilho excessivo intermitente | Gráficos | Não reproduzido (clarões conferidos com o original) |
| 6 | Cores e efeitos especiais incorretos | Gráficos | Parcial: batem com o original; um artefato de 1 frame visto |
| 17 | Sombras incorretas | Gráficos | Resolvido na primeira missão |
| 18 | Sombras em posição errada durante o gameplay | Gráficos | Resolvido na primeira missão |
| 7 | Conclusão de missões | Gameplay | Validado na primeira missão (teste manual) |
| 8 | Jogo completo não validado | Gameplay | Parcial: todos os 10 capítulos carregam e rodam; conclusão só validada na STG02 |
| 9 | Estabilidade prolongada | Estabilidade | Parcial (~70 min e ~25 carregamentos de fase sem falhas) |
| 10 | Quadros pesados limitados pela montagem de comandos do jogo | Desempenho | Em aberto (pior trecho de 5 s ~47 fps; meta de 60) |
| 11 | Áudio depende do firmware local | Áudio | Limitação conhecida |
| 12 | Codec ATRAC não exercitado | Áudio | Não usado em nenhum capítulo testado |
| 19 | Áudio quebra na missão do capítulo 4 (STG08) | Áudio | Corrigido (depende de mudança no SDK) |
| 20 | Aviso do motor de som com 176566 Hz | Áudio | Em análise |
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

### 5. Brilho excessivo intermitente — Não reproduzido
- **Relato inicial:** um frame posterizado em amarelo e vermelho na entrada da missão, quando ainda havia redesenho repetido (item 1).
- **Verificação (25/10/2026):** um frame por segundo durante boot, menus, cena de abertura e combate com golpes especiais, medindo brilho médio, pixels estourados e número de cores. Nenhum frame posterizado (todos os frames de combate têm 180-230 mil cores). Os únicos frames brancos são o fade para branco e o clarão da cena de abertura ("俺の名は『ウィザード』"), e uma gravação do jogo original (YouTube `u4YixUZPH30`, a partir de 3:05) tem a mesma sequência: fade para branco, cerca de 2 s de preto e novo clarão que se desfaz na cena do portão. Os clarões dos golpes especiais têm o tamanho dos do original.
- **Conclusão:** não reproduzido nas versões atuais. O chão escurecido pelas sombras erradas (item 17) mudava bastante o brilho da cena e pode ter contribuído para o relato.

### 6. Cores e efeitos especiais incorretos — Parcial
- **Verificação (25/10/2026):** comparado com a mesma gravação do original: os efeitos dos golpes (círculos mágicos vermelhos, fogo, água do estilo Water, o braço-canhão) e a iluminação do combate batem. A cena do holofote só ficou igual depois das correções de sombra (item 17).
- **Ainda visto:** num único frame, no início de um golpe especial, um polígono grande, bege e sem textura cortou a parte de baixo da tela na diagonal. Não se repetiu em outras capturas; a causa não foi encontrada.

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

### 8. Jogo completo — Parcial
- **Teste (29/10/2026):** com um save do RPCS3 que tem o modo história inteiro concluído (todos os modos do menu destravados), a primeira missão de cada um dos 10 capítulos do Chronicle foi aberta e jogada pelo piloto automático (`PAD_FILE`/`PORT_PAD_STICK_FILE`, 1,5 a 8 min cada), numa única sessão de ~70 min, com a janela aberta.
- **Resultado:**

| Capítulo | Fase | Resultado |
|---|---|---|
| Prólogo | STG02 | Carrega e roda; cena do holofote e combate normais |
| 英雄の目覚め (1) | STG02 | Carrega e roda |
| 英雄の目覚め (2) | STG09 | Carrega e roda |
| 英雄の目覚め (3) | STG03 | Carrega e roda; missão de moto com tempo: o piloto automático não termina a tempo e o jogo mostra "Mission Failed" e a tela de resultado normalmente |
| Chronicle 1章 | STG05 | Carrega e roda |
| Chronicle 2章 | STG11 | Carrega e roda; pilotagem da moto normal |
| Chronicle 3章 | STG10 | Carrega e roda |
| Chronicle 4章 | STG08 | Carrega e roda; **áudio quebra a missão inteira** (item 19) |
| Chronicle 5章 | STG12 | Carrega e roda |
| Capítulo final | STG19 | Carrega e roda 8 min: lutas contra Decade e Skull, troca de formas, especiais; o W foi derrotado e o jogo foi para o resultado e "tentar de novo" normalmente |

- Nenhum travamento ou erro do port no log; média de 55 fps na sessão inteira (59,4 fps nos 8 min da missão final).
- **Falta:** concluir as missões (o piloto automático não termina missões; ver item 7), as demais ~20 missões dos capítulos, o final e os créditos (`MEN_ENDING.msf`, `MEN_STAFFROLL.msf`), Rider Road, Free Mission e Galeria. Isso exige jogar manualmente.

### 9. Estabilidade prolongada — Parcial
Houve ~30 min de missão contínua sem travamento e sem erros no log, até o limite de tempo do script de teste. Sessões mais longas, troca de fases e carregamentos repetidos não foram testados.

### 10. Quadros pesados limitados pela montagem de comandos do jogo — Em aberto
- **Medido (25/10/2026, linha do tempo `PS3_FTRACE` em luta na STG02):** um quadro é o processamento do FIFO pela thread `frame_clock` (~12,5 ms) seguido do trabalho da thread `main` depois da fence do quadro (~5,6 ms). Nos quadros acima de 20 ms, o FIFO continua em ~13 ms e a `main` passa a ~10,5 ms; 72% dela está na montagem da lista de comandos (`func_005B2930`, bloco traduzido `020`). A afirmação abaixo, de 24/10, de que a thread principal estava saturada a 98%, não vale mais: em combate nenhuma thread passa de ~80%, e elas esperam umas pelas outras.
- **Feito em 25/10/2026** (A/B intercalado, `scripts/bench_combat.py`): núcleo físico próprio para as threads mais ocupadas (`thread_affinity.c`); render targets que eram recriados todo quadro mantidos em cache; busca de vértices, leitura de índices e hash do pipeline mais rápidos no processamento do FIFO; caminho rápido para todas as escritas do código traduzido (`store_wrap.c`). Média em luta: ~48 → ~58 fps; pior trecho de 5 s: ~45 → ~47.
- **Testados e rejeitados em 25/10/2026:** GameMode (sem efeito nesta máquina), C do runtime em `-O3`, folga de timer de 1 µs, intervalo menor entre publicações de fence, caminho rápido inline nos blocos 016 e 020, PGO retreinado em luta e GCC 12.3 (58,2 contra 58,4 fps).
- **Próximo passo possível:** melhorar o código que o tradutor do ps3recomp gera para a montagem de comandos (manter registradores do PPU em variáveis locais etc.), uma mudança no SDK.

#### Histórico (24/10/2026)
- **Medido (24/10/2026, perfil de CPU por thread em combate pesado na STG02):** sempre que o fps cai abaixo de ~50, a thread PPU principal do jogo fica em 98% de um núcleo; áudio (~45%), FIFO/Vulkan (~50%) e a outra thread PPU (~30%) têm folga. O fps nas quedas depende só da velocidade dessa thread.
- **Feito desde então** (detalhes em `docs/PERFORMANCE.md`): leituras de relógio removidas dos locks de mutex do jogo (frames acima de 33 ms: 52 → 17), código traduzido em huge pages, e PGO treinado na primeira missão (pior trecho de 5 s: 35 → 43 fps na AppImage). Testados e rejeitados: huge pages na memória do jogo e o caminho rápido de memória em mais blocos gerados.
- **Ainda em aberto:** um teste manual antes da v0.4.0 relatou ~25 fps nas lutas mais pesadas no Ryzen 5 4600H (~40 fps num Ryzen 7 5700X); não foi remedido com a v0.4.x. Opções restantes: instruções FMA (`-mfma`, uma decisão de portabilidade) e um GCC mais novo no toolchain da AppImage (~+5% medido com o GCC 16).

### 11. Áudio depende do firmware local — Limitação conhecida
A tradução do codec MP3 só é gerada se o `flashMP3.pic` local tiver o SHA-256 verificado. Sem ele, o codec fica interpretado e o combate provavelmente volta a ter cortes. Sem nenhum codec, a tarefa de áudio para (ver `README_FIRMWARE.md`).

### 12. Codec ATRAC — Não usado nas fases testadas
O jogo não abriu o `flashATRAC.pic` nos testes, nem na sessão de 29/10/2026 que passou pelos 10 capítulos. Todas as músicas (`sound/BGM/BGM/*.msf`) são MPEG estéreo; se o ATRAC for usado em algum lugar, roda interpretado e pode ter cortes.

### 19. Áudio quebra na missão do capítulo 4 (STG08) — Corrigido (depende de mudança no SDK)
- **Sintoma (29/10/2026):** na primeira missão do Chronicle 4章 ("近くて遠い", fase `stg08.gtc`), 60-75% dos blocos de áudio chegam vazios do começo ao fim da missão (`PORT_AUDIO_STATS`: ~680 underruns de 938 por linha), começando já em `MIS_ENTER.msf`. Em todas as outras fases testadas ficam abaixo de 0,4%.
- **Não é a música:** `MIS_EVENT_BATTLE_BOSS.msf`, que toca nessa missão, também tocou na missão final sem cortes.
- **Pista:** no log, cada execução da tarefa de áudio do SPU (`[spu_workload] WAIT_SIGNAL ... ran=`) leva 29-39 ms durante essa missão, contra 0-6 ms no resto da sessão.
- **Causa:** `PORT_SPU_PROFILE` mostrou ~3,7 bilhões de passos interpretados em 0x37000-0x397C0. Ali a tarefa carrega, sem relocação e a partir de LS 0x36F80, um módulo SPU de 10 KB embutido no `EBOOT.ELF` (offset 0x686D00; não é codec do firmware). Essa fase roda o módulo em todo bloco de áudio.
- **Correção, em duas partes:**
  - `scripts/lift_audio_spu.py` traduz também esse módulo (72 funções, nenhuma instrução sem suporte), como já fazia com o `flashMP3.pic`; `spu_bridge.c` aceita várias sobreposições. Sozinho, isso baixou as falhas para 2-20%: o código traduzido do módulo virou ~46% do tempo da thread de áudio.
  - No SDK (`runtime/spu/spu_helpers.h`), `rotqby`, `rotqbyi`, `shlqbyi` e `cwd` não tinham caminho vetorial em x86 (só em NEON) e viravam laços byte a byte. Com versões SSE4.1 (`pshufb`), idênticas à referência em teste exaustivo com gcc e clang, a função mais quente do módulo caiu de 11037 para 8244 instruções.
- **Resultado (build PGO, 29/10/2026):** na mesma missão, 0,2% de underruns no combate da primeira fase e 0 em 3 minutos da segunda; a missão final continua limpa (8 de 26264). O chefe dessa missão não foi alcançado pelo piloto automático.
- **Pendente:** a mudança no SDK está só na cópia local de `../ps3recomp`; o AppImage empacota a revisão fixada em `recompile.json`, então ela precisa entrar no SDK (e a revisão ser atualizada) para chegar aos jogadores.

### 20. Aviso do motor de som com 176566 Hz — Em análise
- O motor de som do jogo escreveu 4 vezes `SCREAM: Error! Sound buffer size is too small for this playback frequency (176566 Hz)` na missão final, logo depois de abrir a fala `VOICE/SKL/SKL_050.msf` (Skull). 176566 Hz é ~3,7× 48 kHz; não se sabe se é um tom alterado legítimo do jogo ou uma frequência calculada errado no port. Ainda não foi comparado com o jogo original.

### 13. Encerramento limpo — Em aberto
Execuções com limite de tempo às vezes exigem SIGKILL (já anotado no `docs/BUILD.md`).

### 14. Processos de teste remanescentes — Contornado
Um processo antigo do jogo sobreviveu ao `pkill -f` e rodou junto com o novo, contaminando duas medições. Os testes passaram a encerrar o jogo pelo PID e a confirmar que nenhum processo ficou rodando.

### 15. Toques curtos do `PAD_FILE` perdidos — Contornado
Com o jogo mais rápido, toques de 8 polls às vezes não eram registrados (o START da abertura, o ○ da escolha de dificuldade). Os scripts passaram a segurar os botões por mais tempo.

### 16. Personagem não se move pelo direcional — Contornado
Neste jogo o personagem só anda pelo analógico esquerdo, e o SDK só permite fixar o analógico desde o início (`PAD_STICK`). `PORT_PAD_STICK_FILE` (commit `1a8c94a`) permite controlar os dois analógicos por arquivo durante os testes.

### 18. Sombras em posição errada durante o gameplay — Resolvido na primeira missão
- **Sintoma (teste manual, 25/10/2026):** durante o gameplay, as sombras apareciam deslocadas, como silhuetas soltas na diagonal, longe dos pés dos personagens.
- **Causa:** o jogo desenha o *shadow map* num buffer de profundidade de 1024×1024, mas o motor cria o buffer com o tamanho que cobre a tela inteira, 1280×1024 (`eng_zdepth_get`). A cópia usada como textura pegava o buffer todo, e o shader lê com coordenadas normalizadas: o mapa ficava esticado 1,25× na horizontal, e cada sombra saía deslocada, mais longe quanto mais à direita no mapa.
- **Correção:** `eng_zdepth_snapshot` copia só o tamanho que a textura do jogo declara (1024×1024, a partir do canto superior esquerdo). `PORT_DEPTH_SNAPSHOT_FULL=1` volta ao comportamento anterior para comparação.
- **Verificado:** quadros da luta na STG02 antes e depois (gravados com `scripts/bench_combat.py --dump`), comparados com a gravação do jogo original (YouTube `u4YixUZPH30`): com a correção, a sombra de cada personagem sai dos pés, curta e para trás, como no original; antes, aparecia solta na diagonal. A cena do holofote, que usa o mesmo mapa, continua igual ao original (sombra longa saindo dos pés para baixo e à direita). Outras missões não foram verificadas.
