# Reprodução cellSail neste port

O port usa `sail_bridge.cpp` e `sail_decoder.hpp` para reproduzir vídeo PAMF
por meio dos executáveis `ffmpeg` e `ffprobe` instalados no sistema. O áudio
ATRAC3plus é demultiplexado dos pacotes privados do PAMF e decodificado pela
biblioteca ATRAC já incluída no SDK. Não precisa dos pacotes de desenvolvimento
do FFmpeg. O SDK original permanece intacto.

Os imports do jogo são registrados com handlers que recebem os registradores
PPU diretamente. Isso preserva os endereços guest e os argumentos de 64 bits,
incluindo os tokens de conclusão assíncrona. As estruturas de formato e frame
são gravadas em big-endian. As assinaturas foram conferidas em
[cellSail.h do RPCS3](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/Emu/Cell/Modules/cellSail.h).

## Funcionamento

- Boot, abertura, início, parada e fechamento passam por uma fila processada
  pelo relógio de quadros. Os callbacks de player e adaptadores executam pelo
  dispatcher guest. A thread de decodificação nunca chama código do jogo.
- Os descritores conservam a URI e resolvem somente arquivos de `/dev_bdvd`
  dentro de `PS3_VFS_ROOT`. Travessia de diretórios e symlinks para fora da raiz
  são rejeitados. Nenhum caminho é interpolado em um comando de shell.
- O probe identifica resolução e taxa de quadros. O decoder força o demuxer
  MPEG, necessário porque `.pam` também é uma extensão de formato de imagem.
- O FFmpeg entrega pixels ARGB/RGBA ou YUV422. Há no máximo quatro quadros na
  fila do host e três buffers guest, obtidos pelo callback de alocação do jogo
  quando ele é fornecido. Pitch, tag, sessionId e PTS acompanham cada quadro.
- GetFrame2 respeita a taxa do vídeo e a pausa. O fim do arquivo gera SOURCE_EOS
  somente quando o decoder termina sem erro e todos os quadros foram entregues.
  Após entregar o último quadro, o player retorna a OPENED. Isso permite que
  o jogo reconheça o término natural sem simular uma chamada Stop do usuário.
- Stop cancela o processo de decode e recolhe a thread; Close libera os buffers.
  Falhas do decoder geram erro, em vez de fingir reprodução concluída.
- O áudio sai em PCM float32 big-endian pelo SoundAdapter, com formato,
  sessionId, tag e PTS. O mixer do próprio jogo entrega esses dados ao cellAudio.
  O fim do player espera a entrega dos últimos quadros de vídeo e áudio.
- `audio_bridge.c` conserva o HLE de áudio do SDK e corrige a cadência da thread
  POSIX no Linux: acompanha o dispositivo em vez de consumir blocos por um
  intervalo fixo. `AUDIO_WAV=/caminho/mix.f32le` grava a saída final estéreo a
  48 kHz; `AUDIO_PEAK=1` registra o pico dessa saída para diagnóstico.

## Validação

```bash
cmake --build --preset linux-vulkan
bash tests/test_sail.sh
SANITIZE=1 bash tests/test_sail.sh
SANITIZE=1 bash tests/test_sail_audio.sh
PORT_TEST_SECONDS=300 ./run-vulkan.sh
```

O teste usa um vídeo sintético de seis quadros. Verifica callbacks adiados,
tokens de 64 bits, validação de estado e caminhos, erro de alocação, frames
reais, pausa, fim de arquivo, Stop explícito, cancelamento e falha de decoder.
O modo SANITIZE usa AddressSanitizer e UndefinedBehaviorSanitizer; a detecção
de vazamentos fica desativada porque o ambiente do aplicativo impede sua inspeção.
O teste de áudio usa o PAMF original: valida 6.533.120 amostras por canal,
energia não nula, valores finitos, cancelamento e rejeição de frame truncado.

## Limites

Esta é uma implementação para os imports usados por BLJS10220, não uma
implementação completa do cellSail. O demux de áudio aceita a primeira faixa
ATRAC3plus mono/estéreo a 48 kHz, com até 32 MiB de dados comprimidos. Outros
codecs de áudio, seek, repetição e alguns formatos de imagem seguem pendentes. As
opções de reprodução não suportadas retornam erro. A conversão de PTS e a
cadência usam a taxa constante identificada pelo probe.

Os testes deste componente alcançaram a tela de título com “PRESS ○ BUTTON”.
O início da missão foi validado posteriormente; veja o estado atual no README.
As pastas `analysis/sail-av-*` e `analysis/sail-video-*` são logs locais,
excluídos da publicação. Não acompanham o pacote de fontes.

Para diagnóstico, `PORT_SAIL_TRACE=1` registra os estados internos do player
usados por este jogo. `PORT_SAIL_TEST_MOVIE=/caminho/arquivo.pam` substitui
somente a fonte de vídeo desta execução por uma fixture separada, permitindo
testar o fim de reprodução rapidamente. Nenhuma dessas opções está ativada no
iniciador normal; a segunda é exclusivamente para testes e não modifica os
arquivos originais do jogo.
