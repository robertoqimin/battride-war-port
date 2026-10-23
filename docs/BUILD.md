# Compilar a partir do código publicado

Este pacote contém código do port, configurações e um patch pequeno de integração. Os arquivos do jogo, firmware e fontes completas geradas de PPU/SPU ficam apenas no computador de quem compila. Não há download automático desses dados.

## Ambiente validado

Fedora 44 x86_64, clang 22, GCC 16, CMake 4, Ninja e NVIDIA GTX 1650. O projeto usa C17/C++20 e Python 3.11 ou superior. Outras distribuições e GPUs ainda precisam de validação.

Os nomes abaixo correspondem aos pacotes usados neste Fedora. Instale no seu terminal:

```bash
sudo dnf install git patch cmake ninja-build clang gcc-c++ python3 python3-pip \
  sdl2-compat-devel vulkan-headers vulkan-loader \
  glslang glslang-devel spirv-tools-devel pkgconf-pkg-config ffmpeg-free
```

É necessário um driver Vulkan funcional para a GPU. `ffmpeg` e `ffprobe` precisam estar no PATH para os vídeos PAMF. Não são necessários headers de desenvolvimento do FFmpeg nem spirv-cross para o backend Vulkan deste port.

## 1. Fixar o SDK

Mantenha o checkout oficial ao lado do diretório deste port:

```text
pasta-de-trabalho/
  ps3recomp/
  kamenriderbattridewarsport/
```

Execute na pasta de trabalho, criando um checkout novo do SDK:

```bash
git clone https://github.com/sp00nznet/ps3recomp.git
cd ps3recomp
git checkout --detach a6d76c895f77eb30b90a806c830544e61821b77f
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements.txt
cd ../kamenriderbattridewarsport
```

Se o SDK já existir, não clone nem substitua a pasta: confira o commit e preserve alterações locais. Os arquivos locais `*_bridge.*` dependem das interfaces dessa revisão. Atualizar o SDK exige nova validação.

## 2. Preparar os dados locais

Use a extração local do seu disco e o ELF descriptografado correspondente a **BLJS10220**:

```text
kamenriderbattridewarsport/
  game/
    EBOOT.ELF
    PS3_GAME/
      PARAM.SFO
      USRDIR/
        nativePS/
          ...arquivos do jogo...
```

O SHA-256 esperado de `game/EBOOT.ELF` é:

```text
a53b7bca5d47490710ba02af5f885e1219d10c7a1a456fcf6e13a48db668a014
```

Confira com `sha256sum game/EBOOT.ELF`. Outro executável, atualização ou região não está validado: os endereços do patch e da ponte SPU são específicos desta versão. Este repositório não fornece ISO, EBOOT, chaves, firmware, assets ou saves.

Os codecs de firmware são opcionais para compilar, mas necessários para os caminhos de áudio usados pelo jogo. Consulte [README_FIRMWARE.md](../README_FIRMWARE.md) para posicionar arquivos obtidos localmente.

## 3. Gerar PPU/SPU e aplicar o patch

Na raiz do port, em um checkout novo:

```bash
../ps3recomp/.venv/bin/python scripts/generate.py --jobs 4
```

O script confere o commit do SDK e o hash do ELF, analisa o executável, gera os 84 arquivos PPU, aplica `patches/graphics-command-buffer-init.patch` sem fuzz e gera os programas SPU aceitos. Ele se recusa a substituir `src/recomp/`, `spu/` ou `analysis/regeneration/` existentes. Para conferir apenas os pré-requisitos, use `--verify-only`. Para outro local do SDK, acrescente `--sdk /caminho/ps3recomp`.

A geração PPU produz cerca de 593 MiB de fontes; reserve espaço também para objetos e executável. Em uma máquina com pouca RAM, diminua `--jobs` e o paralelismo de compilação.

A geração SPU usa `--allow-partial` de propósito: das duas imagens detectadas, apenas a imagem `615f0131…dc0657` é registrada estaticamente. A imagem de áudio rejeitada usa o interpretador de `spu_bridge.c`; não se trata de tradução estática completa. O registro gerado é conferido antes de instalar os resultados. Todos esses resultados são ignorados pelo Git.

As ferramentas e opções utilizadas pelo script são:

```text
ppu_loader.py game/EBOOT.ELF -o <analise>
ppu_lifter.py game/EBOOT.ELF --functions <analise>/EBOOT.functions.json
  --hle-stubs <analise>/EBOOT.imports.json --output <fontes-ppu>
  --jobs 4 --chunk-lines 80000
patch --batch --fuzz=0 -p1 -i patches/graphics-command-buffer-init.patch
build_spu_workloads.py --input game/EBOOT.ELF --lifted <fontes-spu>
  --out <fontes-spu>/spu_workloads.c --constructor --allow-partial
```

Use o script para executar a sequência: ele organiza as pastas temporárias e as verificações. O `config.toml` é uma configuração de referência; esta geração é controlada pelas opções acima e por `recompile.json`.

## 4. Compilar e abrir

```bash
cmake --preset linux-vulkan \
  -DPython3_EXECUTABLE="$PWD/../ps3recomp/.venv/bin/python"
cmake --build --preset linux-vulkan
./run-vulkan.sh
```

Para outro local do SDK, acrescente `-DPS3RECOMP_DIR=/caminho/ps3recomp` na configuração. Confira no resultado do CMake que o Vulkan informa `guest programs available`: sem glslang os shaders do jogo não funcionam corretamente. O SDK carrega o Vulkan dinamicamente.

O jogo usa a árvore `game/` como VFS e cria instalação/saves em `gamedata/`. O lançador habilita a janela, os shaders e os buffers ampliados. Não há prazo automático de encerramento; `PORT_TEST_SECONDS=300 ./run-vulkan.sh` limita um diagnóstico. O fechamento gracioso não está validado em todos os caminhos; os testes limitados às vezes precisaram de SIGKILL.

## 5. Verificar

```bash
python3 -m unittest discover -s tests -p test_publication.py
python3 scripts/export_source.py
bash tests/test_graphics_buffers.sh
bash tests/test_gcm_jump.sh
bash tests/test_sail.sh
```

Os testes C/C++ precisam dos resultados de geração/compilação conforme suas dependências. A regressão de áudio utiliza o PAMF local do disco:

```bash
bash tests/test_sail_audio.sh
```

Para conferir a leitura por posição:

```bash
c++ -std=c++20 -O0 -ffunction-sections -fdata-sections \
  -Isrc/recomp -I../ps3recomp/include -I../ps3recomp/runtime/ppu \
  tests/test_fs_offset.cpp -Wl,--gc-sections -o build-vulkan/test_fs_offset
./build-vulkan/test_fs_offset
```

Nenhum teste publica arquivos no GitHub. A compilação não instala dependências nem busca dados do jogo automaticamente.
