# gnome-session-bin Deb 打包摘要

## 目标

为当前 Meson 工程增加一个可选的 Debian 打包目标，使构建目录可以直接生成 `gnome-session-bin` 的 `.deb` 文件。

支持的目标名：

- `ninja -C _build gnome-session-bin-deb`
- `ninja -C _build deb`

输出文件位于构建目录下，例如：

- `/root/gnome-session/_build/gnome-session-bin_42.0-1ubuntu2_arm64.deb`

## 修改点

只改了两处：

1. 顶层 `meson.build`
2. `tools/build-gnome-session-bin-deb.py`

其中：

- `meson.build` 只负责注册 Meson `custom_target()` 和别名目标。
- `build-gnome-session-bin-deb.py` 负责 staging、筛选文件、生成 control、生成 md5sums、调用 `dpkg-deb`。

## 打包流程

脚本的处理步骤：

1. 调用 `meson install -C <builddir> --destdir <staging> --no-rebuild --quiet`
2. 从 staging 中挑出需要进入 `gnome-session-bin` 的文件子集
3. 从当前系统已安装包复制发行版附加文件：
   - `/usr/libexec/run-systemd-session`
   - `/usr/share/doc/gnome-session-bin/changelog.Debian.gz`
   - `/usr/share/doc/gnome-session-bin/copyright`
4. 额外创建兼容链接：
   - `/usr/lib/gnome-session/run-systemd-session -> ../../libexec/run-systemd-session`
5. 通过 `dpkg-query -s gnome-session-bin` 读取当前系统包 control 信息
6. 生成新的 `DEBIAN/control` 和 `DEBIAN/md5sums`
7. 调用 `dpkg-deb --root-owner-group --build`

## control 字段复刻范围

当前实现会从系统已安装的 `gnome-session-bin` 复刻这些字段：

- `Package`
- `Source`
- `Version`
- `Section`
- `Priority`
- `Architecture`
- `Maintainer`
- `Original-Maintainer`
- `Depends`
- `Recommends`
- `Breaks`
- `Description`

有两个字段不会按字面原样照抄：

1. `Status`
   - 这是已安装包在本机 dpkg 数据库里的状态字段。
   - 生成新的 `.deb` 时不应写入 control。

2. `Installed-Size`
   - 当前脚本会按新包实际内容重新计算。
   - 因为本地重新编译后的二进制体积可能与系统仓库中的预编译包不同，所以这个值通常不会完全一致。

## 当前方案的边界

这是一个“最小侵入”方案。

优点：

- 不需要改各个子目录的 Meson target 定义
- 包装逻辑集中在一个脚本里
- 可以直接在当前工程上启用 deb 打包

限制：

- 该目标依赖现有 build 产物已经可用
- 更适合先执行普通编译，再执行 `ninja -C _build gnome-session-bin-deb`
- 如果希望在全新构建目录里直接一步完成“先编译所有需要文件，再自动打包”，则需要继续把子目录 target 显式挂到打包 target 的依赖上

## 已验证结果

已确认：

- `.deb` 文件生成在 `_build/` 目录下
- 包名为 `gnome-session-bin`
- 版本和架构来自当前系统已安装包
- control 主要字段与当前系统包一致
- 包内容包含目标文件清单中的运行时文件、Debian 文档和 `run-systemd-session` 兼容链接