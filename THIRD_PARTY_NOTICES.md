# Créditos e componentes externos

## PS3Recomp

- Projeto: https://github.com/sp00nznet/ps3recomp
- Revisão usada: `a6d76c895f77eb30b90a806c830544e61821b77f` (0.11.0).
- Copyright (c) 2026 Ned Heller / sp00nznet.
- Licença MIT: texto integral preservado em `LICENSE`.

O projeto começou com o template do PS3Recomp. `CMakeLists.txt`, `config.toml`, o scaffold de `main.cpp` e partes de `stubs.cpp` derivam desse template. As cópias locais adaptadas são:

| Arquivo do port | Origem no SDK |
| --- | --- |
| `loader_bridge.cpp` | `runtime/ppu/ppu_loader.cpp` |
| `gcm_bridge.c` | `libs/video/cellGcmSys.c` |
| `rsx_engine_bridge.c` | `libs/video/rsx_draw_engine.c` |
| `vulkan_bridge.c` | `libs/video/rsx_vulkan_backend.c` |

`audio_bridge.c` e `fs_bridge.cpp` incluem implementações do SDK durante a compilação. As fixtures FIFO de `tests/test_gcm_jump.c` também derivam dos testes do SDK. O checkout oficial permanece separado, com suas licenças e avisos originais.

## Dependências obtidas separadamente

O pacote de fontes não inclui SDL, Vulkan, glslang, SPIR-V Tools, FFmpeg ou seus binários. Cada dependência conserva seus próprios termos e avisos. Não se deve interpretar a licença MIT deste pacote como licença dessas dependências.

O SDK inclui um decoder ATRAC3/ATRAC3plus em `third_party/at3_standalone`, derivado do FFmpeg e obtido do PPSSPP, sob LGPL-2.1-or-later. Este ZIP não contém esse decoder, mas o executável produzido pela compilação o incorpora. Antes de distribuir um binário, examine os arquivos `README` e `COPYING.LGPLv2.1` desse componente e os avisos das demais dependências. Este preparo é para publicação de fontes, sem uma release binária.

RPCS3 foi usado como referência de interfaces de firmware e, no ambiente local de desenvolvimento, para extrair firmware fornecido pelo usuário. O pacote não inclui seu executável nem os arquivos extraídos.

## Jogo e firmware

Kamen Rider: Battride War e seus assets não integram este pacote de fontes. Não há afiliação ou endosso dos titulares do jogo. Firmware Sony, codecs `.pic`, chaves, saves, ELF do jogo e fontes completas geradas de PPU/SPU são dados locais e não estão cobertos pela licença deste repositório.
