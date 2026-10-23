# Local audio firmware

The published code does not include firmware, codecs, or keys. Obtain these files locally from your own firmware/console data and keep them out of Git.

The launcher looks for:

```text
firmware/dev_flash/sys/external/flashMP3.pic
firmware/dev_flash/sys/external/flashATRAC.pic
```

You can also use an external installation without copying files into the port:

```bash
PS3_DEV_FLASH=/path/to/dev_flash ./run-vulkan.sh
```

`PS3_DEV_FLASH` must point to the `dev_flash` root containing `sys/external/`. The explicit variable takes precedence over the local default.

During development on Fedora, the codecs were extracted from firmware on the user's disc using an isolated RPCS3 configuration. Without them, the audio SPU task stopped upon entering missing code, leaving the PPU waiting for an EventFlag. With the files present, the game opened the MP3 codec and the task remained active during the menu test, without fabricating completion signals.

The codecs are not required to compile the host code. They are runtime data required for these audio paths; their absence may affect audio and game progression. The PAMF opening uses a separate ATRAC3plus decoder supplied by the SDK. Audio still has interruptions and has not been validated as continuous.

`firmware/`, `*.pic`, and `*.pup` are ignored. Do not add them with `git add -f` or attach them to a port release.
