# kamenriderbattridewarsport

Port **experimental** de Kamen Rider: Battride War (Japan), **BLJS10220**, usando PS3Recomp 0.11.0 e Vulkan no Linux. Não há afiliação com os titulares do jogo.

Este repositório contém código do port, configurações, testes e instruções. **Não inclui jogo, ISO, EBOOT, firmware, chaves, saves, executável compilado ou fontes completas geradas de PPU/SPU.** Cada pessoa precisa preparar seus dados locais e gerar as fontes antes de compilar.

## Estado validado em 22/10/2026

- Abertura PAMF com callbacks `cellSail`; fim de reprodução e chegada ao título foram validados em etapas anteriores.
- Leitura `cellFsReadWithOffset`, instalação dos dados e adaptadores de save implementados. No ambiente testado, 21.107 arquivos instalados foram comparados por SHA-256 com os arquivos do disco, sem diferenças.
- Texturas de vértices implementadas no backend Vulkan local, permitindo renderizar a animação do personagem.
- Início da missão **STG02** alcançado: cenário, personagem, inimigos, HUD, movimento, pausa/resumo e ataques observados. O contador chegou a **5 Combo**. Uma sessão de aproximadamente 557 segundos foi encerrada intencionalmente; o save original permaneceu inalterado.
- A missão inicial pode produzir cerca de 19 MiB de comandos neste runtime. Os buffers originais de 4 MiB ultrapassavam seus limites e atingiam dados do renderizador. Dois buffers separados de 32 MiB evitam essa sobrescrita no trecho testado, consumindo 64 MiB adicionais de memória convidada. É uma solução de capacidade; a origem do tráfego excessivo permanece em investigação.

**Ainda não é uma experiência fluida:** desempenho muito baixo e variável, brilho excessivo intermitente e efeitos/cores incorretos. Derrota de inimigos, conclusão de missão, jogo completo e estabilidade prolongada não foram validados. O áudio ainda tem interrupções.

A sessão longa de gameplay usou uma substituição PAMF de seis segundos apenas para acelerar a introdução. Os assets originais não foram alterados; o lançador normal continua usando o vídeo original. A sequência inteira com esse vídeo não foi repetida na última etapa de gameplay.

## Preparar e compilar

Siga [docs/BUILD.md](docs/BUILD.md): dependências do Fedora, revisão fixa do SDK, layout dos dados, hash do EBOOT, geração PPU/SPU e aplicação do patch.

Depois de preparar o SDK e os dados locais num checkout novo:

```bash
../ps3recomp/.venv/bin/python scripts/generate.py --jobs 4
cmake --preset linux-vulkan \
  -DPython3_EXECUTABLE="$PWD/../ps3recomp/.venv/bin/python"
cmake --build --preset linux-vulkan
./run-vulkan.sh
```

A geração se recusa a sobrescrever resultados existentes. São esperados cerca de 593 MiB de fontes PPU e espaço adicional para compilar. A compilação usa clang para C e GCC para C++.

## Componentes do port

- `spu_bridge.c`: interpretação da tarefa de áudio rejeitada pelo tradutor estático; outra imagem SPU é gerada e registrada estaticamente.
- `sail_bridge.cpp`, `sail_decoder.hpp`, `sail_audio.hpp`: callbacks, vídeo e áudio PAMF. Detalhes em [README_SAIL.md](README_SAIL.md).
- `audio_bridge.c`, `fs_bridge.cpp`: extensões locais do áudio e VFS do SDK.
- `gcm_bridge.c`, `rsx_engine_bridge.c`, `vulkan_bridge.c`, `loader_bridge.cpp`: adaptações locais de implementações do SDK; o checkout oficial permanece separado.
- `stubs.cpp`: adaptadores HLE do jogo e alocação dos buffers gráficos.
- `patches/graphics-command-buffer-init.patch`: chamada mínima de integração a aplicar após gerar PPU.

Os codecs locais de firmware e seus limites estão descritos em [README_FIRMWARE.md](README_FIRMWARE.md).

## Publicação e licença

A lista de arquivos públicos é `PUBLIC_FILES.txt`. Para auditar o conteúdo e preparar um ZIP de fontes:

```bash
python3 scripts/export_source.py
```

Veja [docs/PUBLISHING.md](docs/PUBLISHING.md) para empacotar ou publicar com Git. O preparo não executa upload automaticamente.

Licença MIT, preservando o aviso do PS3Recomp em [LICENSE](LICENSE). Origens dos arquivos adaptados e dependências com outras licenças: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Não há release binária neste pacote.
