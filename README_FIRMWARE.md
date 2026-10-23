# Firmware de áudio local

O código publicado não inclui firmware, codecs ou chaves. Obtenha os arquivos localmente a partir do seu próprio firmware/dados de console e mantenha-os fora do Git.

O lançador procura:

```text
firmware/dev_flash/sys/external/flashMP3.pic
firmware/dev_flash/sys/external/flashATRAC.pic
```

Também é possível usar uma instalação externa sem copiar arquivos para o port:

```bash
PS3_DEV_FLASH=/caminho/dev_flash ./run-vulkan.sh
```

`PS3_DEV_FLASH` deve apontar para a raiz de `dev_flash`, que contém `sys/external/`. A variável explícita tem prioridade sobre o padrão local.

No desenvolvimento em Fedora, os codecs foram extraídos do firmware contido no disco do usuário usando uma configuração isolada do RPCS3. Sem eles, a tarefa SPU de áudio parava ao entrar no código ausente, deixando o PPU aguardando um EventFlag. Com os arquivos presentes, o jogo abriu o codec MP3 e a tarefa permaneceu ativa no teste do menu, sem fabricar sinais de conclusão.

Os codecs não são necessários para compilar o código do host. São dados necessários em tempo de execução para esses caminhos de áudio; sua ausência pode afetar áudio e progresso do jogo. A abertura PAMF usa um decoder ATRAC3plus separado, fornecido pelo SDK. O áudio ainda apresenta interrupções e não está validado como contínuo.

`firmware/`, `*.pic` e `*.pup` estão ignorados. Não os adicione com `git add -f` nem os anexe a uma release do port.
