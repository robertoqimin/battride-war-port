# Publicar o código

`PUBLIC_FILES.txt` é a lista explícita de arquivos deste pacote de fontes. `.gitignore` exclui jogo, firmware, saves, resultados gerados, compilações e logs. Não use `git add -f` nessas pastas.

## Conferir e empacotar

Na raiz do projeto:

```bash
python3 -m unittest discover -s tests -p test_publication.py
python3 scripts/export_source.py
python3 scripts/export_source.py --output /tmp/kamenriderbattridewarsport-source.zip \
  --manifest /tmp/kamenriderbattridewarsport-source-manifest.json
```

Os nomes de saída precisam estar livres. O exportador nunca sobrescreve arquivos existentes. Ele aceita somente os arquivos de texto explicitamente listados, rejeita symlinks e caminhos privados e cria um ZIP sem histórico Git ou dados locais. Essa verificação não substitui a revisão de conteúdo quando o código for alterado futuramente.

Para publicar pela interface do GitHub, extraia esse ZIP e envie os arquivos contidos na pasta, não a sua árvore local inteira.

## Publicar com Git

Crie um repositório vazio no seu GitHub. Depois, na raiz do port, se ainda não houver um repositório Git:

```bash
git init --initial-branch=main
git add --pathspec-from-file=PUBLIC_FILES.txt
git diff --cached --stat
git diff --cached --name-only
```

Confira que não há `game/`, `firmware/`, `gamedata/`, `src/recomp/`, `spu/`, `analysis/` ou `build*/` na lista. Então faça o commit e configure a URL do seu repositório:

```bash
git commit -m "Prepare experimental source release"
git remote add origin https://github.com/SEU_USUARIO/kamenriderbattridewarsport.git
git push -u origin main
```

Substitua `SEU_USUARIO`. Se já houver Git/remote/commits, confira o estado existente e adapte os comandos; não reinicialize nem substitua o histórico. O preparo local não executa commit, cria repositório remoto ou faz push.

Descrição sugerida:

> Port experimental de Kamen Rider: Battride War (BLJS10220) com PS3Recomp e Vulkan. Início da missão validado com movimento, pausa e ataques; desempenho baixo e falhas visuais. Requer dados locais do jogo e geração de PPU/SPU. Sem jogo, firmware, chaves ou saves incluídos.

Não anuncie como jogo completo ou port estável. A documentação descreve exatamente o trecho validado. Licenças e créditos estão em `LICENSE` e `THIRD_PARTY_NOTICES.md`.
