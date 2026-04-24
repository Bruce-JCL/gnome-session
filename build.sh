#/bin/bash
meson setup _build -Dprefix=/usr
ninja -C _build
