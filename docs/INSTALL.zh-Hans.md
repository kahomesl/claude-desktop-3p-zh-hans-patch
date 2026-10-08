# 安装指南

请先读 [`DISCLAIMER.md`](DISCLAIMER.md)。它很短，而且正是说明你需要接受什么的那一部分。

---

## 双击安装（可选）

下面全部步骤都可以改成双击 **`启动Claude中文版.command`** 来完成。
它会执行同样的三条命令并用中文显示进度；它具体做什么、
以及首次双击大概率会遇到的隔离提示，见
[README 的一键安装一节](../README.zh-Hans.md#一键安装双击)。

---

## 开始之前

你需要准备三样东西：

1. **一个可安装的应用版本。** 用 `./zh-patch version` 查看。只有
   [`COMPATIBILITY.md`](COMPATIBILITY.md) 中列出的版本可以安装。若你的版本不在其中，
   请见[从备份安装](#从备份安装)。
2. **一份你自己准备的语言资源。** 本项目不附带任何语言资源，详见
   [`CATALOG-FORMAT.md`](CATALOG-FORMAT.md)。没有它，`apply` 会以退出码 4 停止。
3. **一份未被修改过的源应用副本。** 如果待处理的应用已经被打过补丁，安装会被拒绝。
   动手之前请先备份原始应用。

## 第 1 步 —— 检查，但不写入任何内容

```bash
./zh-patch check --app /Applications/Claude.app --catalog-dir ~/my-catalog
```

输出会列出：版本号、签名身份、将被改写的三个文件、将被移除和新增的 entitlements，
以及你的语言资源覆盖率。

此命令不写入任何文件。如果检查失败，请先解决问题再继续——工具会拒绝安装，
而这个拒绝本身就是功能在正常工作。

退出码：`3` 版本不受支持，`4` 语言资源被拒，`5` 应用结构与预期不符。

## 第 2 步 —— 安装

```bash
./zh-patch apply --app /Applications/Claude.app --target /Applications/Claude-3P-ZH.app --catalog-dir ~/my-catalog
```

`--target` 默认是 `/Applications/Claude-3P-ZH.app`。向该位置写入需要管理员权限；
`apply` 会因权限不足而报错，而不会悄悄写到别处。请选择一个你有写权限的位置，
或者在清楚后果的前提下使用 `sudo`。

实际发生的步骤：

1. 复制源应用。**源应用本身不会被修改。**
2. 改写三个 JavaScript 资源文件，每个改写点都经过"出现次数必须精确匹配"的校验。
3. 把你的语言资源写入副本的 `i18n` 目录，同时使用 `zh-Hans` 与 `zh-CN` 两个名称。
4. 在副本内写入一个记录本次操作的标记文件。
5. 由内向外对副本做 ad-hoc 重签名：剥离受限 entitlements，
   并补上 `com.apple.security.cs.disable-library-validation`。
6. 用 `codesign --verify --deep --strict` 校验结果。

任何一步失败，已部分创建的副本都会被删除，源应用始终不受影响。

## 第 3 步 —— 校验

```bash
./zh-patch verify --target /Applications/Claude-3P-ZH.app
```

这是**静态**校验。它确认签名有效、标记文件存在、磁盘上的语言资源与安装时记录的
摘要一致，以及没有残留任何受限 entitlement。它**无法**确认应用能否启动，
也无法确认界面是否真的显示中文。

输出中出现 `gatekeeper rejected` 是预期结果——见
[What changes](../README.md#what-changes)。

## 第 4 步 —— 启动副本

先退出原版。两者共用同一个用户数据目录，同时运行可能导致写入冲突。

```bash
osascript -e 'quit app "Claude"'
open -n -a /Applications/Claude-3P-ZH.app
```

`-n` 用于在已注册原版的情况下仍强制开启新实例。

## 第 5 步 —— 选择语言

如果界面没有自动变成简体中文，请打开 **Settings → Language**，
选择 Chinese (Simplified) 一项。

如果列表里**根本没有**这一项，请停下。不要手工修改配置文件去强行开启——那样既不会
揭示选择器缺少该语言的原因，还会掩盖真正的故障点。请按
[`TROUBLESHOOTING.zh-Hans.md`](TROUBLESHOOTING.zh-Hans.md) 收集信息后反馈。

## 第 6 步 —— 回退

```bash
osascript -e 'quit app "Claude"'
open -a /Applications/Claude.app
```

这样就够了：原版自始至终没有被修改过。确认原版能正常运行之后，再考虑删除副本。

```bash
./zh-patch rollback --target /Applications/Claude-3P-ZH.app
```

`rollback` 会把副本移到废纸篓，因此是可逆的。它只对带有本工具标记文件的副本生效，
所以不会误删原版应用或你的备份。

你的用户数据位于 `~/Library/Application Support/Claude-3p`（或类似名称的目录），
**不受**本工具管理。回退时请不要删除它。

---

## 从备份安装

如果你的已装应用已升级到一个不可安装的版本，请改为处理受支持版本的副本。
除了源不同，其余流程完全一致。

```bash
# 1. 趁应用还是受支持版本、尚未自动升级时，先备份原始应用：
cp -R /Applications/Claude.app /Applications/Claude-2.26454.0.app

# 2. 让工具指向备份，而不是正在使用的应用：
./zh-patch check --app /Applications/Claude-2.26454.0.app --catalog-dir ~/my-catalog
./zh-patch apply --app /Applications/Claude-2.26454.0.app --catalog-dir ~/my-catalog
```

备份必须是该版本的真实副本，且签名完整。不要通过修改 `Info.plist` 里的版本号来
"凑合通过"——结构与摘要校验会拒绝它，而这正是预期行为。

请注意：这样做出的副本基于较旧的构建，其行为会与该版本一致，
而不是与你当前安装的较新版本一致。

---

## 安装为命令（可选）

从检出目录直接运行 `./zh-patch` 即可，安装包是可选的。如果你希望 `PATH` 里有一个命令：

```bash
python3 -m pip install --user .
```

这会提供 `claude-zh-patch`，子命令完全相同。

---

## 卸载

```bash
./zh-patch rollback              # 把副本移到废纸篓
python3 -m pip uninstall claude-desktop-3p-zh-hans-patch
```

然后删除你克隆下来的目录。以上都不会触碰你的用户数据。
