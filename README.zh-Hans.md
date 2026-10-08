# claude-desktop-3p-zh-hans-patch

为 macOS 上的 Claude Desktop 安装简体中文界面，作用于一个**独立副本**，
不改动你现有的应用。

本项目是**非官方社区工具**，与 Anthropic **没有任何关联**。

---

## 请先读这一节

这个项目有四点不太一样，而且四点都很重要。

**1. 它不附带任何语言数据。** 本仓库中**没有任何中文翻译资源**——没有消息目录、
没有提取出来的文本，也没有任何下载或提取中文的代码。你必须通过 `--catalog-dir`
自行提供 catalog，并自行负责拥有使用它的权利。在你提供之前，工具什么都装不了。

**2. 它对未经核验的构建直接拒绝。** 只有
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md) 中列出的版本可以安装。
没有任何强制绕过的参数——不是因为忘了加，而是因为对结构未经核对的构建打补丁，
结果只会是一个坏掉的应用和一份看不懂的 bug 报告。

**3. 它只在一台 Mac 上验证过，且那台机器的 SIP 是关闭的——SIP 开启环境下的兼容性尚未确认。**
唯一一次验证是在系统完整性保护（SIP）**关闭**的状态下进行的，而这不是 macOS 的默认状态。
没有在开启 SIP 的 Mac 上测试过，因此那里的表现是未知的。
通过这些检查**并不等于保证**界面一定正常、登录一定能用、或你的某台 Mac 一定能跑起来。
详见下方[已验证环境](#已验证环境)。

**4. 产物是 ad-hoc 签名的。** 修改应用会使原签名失效，因此副本必须以无 Developer ID
的方式重签名。这会带来实际后果，见[会产生哪些变化](#会产生哪些变化)。

---

## 它做什么

1. 把你已安装的 Claude Desktop 复制成一个独立的应用包
   （默认 `/Applications/Claude-3P-ZH.app`）。
2. 改写三个 JavaScript 资源文件，使语言选择器提供并接受 `zh-Hans`。
3. 把你提供的语言资源写入副本的 `i18n` 目录。
4. 对副本做 ad-hoc 重签名，并**移除 ad-hoc 签名无法承载的受限 entitlements**
   （见[签名与 entitlements](#签名与-entitlements)）。
5. 校验结果，并在副本内写入标记文件记录本次操作。

你已安装的应用不会被改动。你的用户数据、第三方网关配置、
以及模型切换工具同样不会被改动。

## 它不做什么

- 不修改 `/Applications/Claude.app`。
- 不触碰 `~/Library/Application Support`。
- 不读取、不存储、不传输任何凭据、令牌或聊天记录。
- 不关闭系统完整性保护（SIP）或 Gatekeeper，也不要求你这么做。
- 不再分发 Anthropic 的应用、代码或翻译。

---

## 环境要求

| | |
| --- | --- |
| 操作系统 | macOS，Apple Silicon（已验证）或 Intel（未验证） |
| Python | 3.9 或更新——系统自带的 `python3` 即可 |
| 应用 | [兼容性矩阵](docs/COMPATIBILITY.md)中列出的可安装版本 |
| 语言资源 | 一份你自己准备、且有权使用的语言资源目录 |
| 磁盘 | 约为应用体积的两倍，再加一份副本 |

`node` 是可选的。若存在，改写后的 JavaScript 会在安装前做语法检查。

请先安装受支持的应用版本。如果你的已装版本已经升级，请保留一份受支持版本的副本，
并用 `--app` 指向它——见[从备份安装](docs/INSTALL.zh-Hans.md#从备份安装)。

---

## 快速开始

```bash
git clone https://github.com/kahomesl/claude-desktop-3p-zh-hans-patch.git
cd claude-desktop-3p-zh-hans-patch
```

检查应用与语言资源，不写入任何内容：

```bash
./zh-patch check --catalog-dir ~/my-catalog
```

`check` 通过后安装：

```bash
./zh-patch apply --catalog-dir ~/my-catalog
```

校验磁盘上的副本：

```bash
./zh-patch verify
```

撤销：把副本移到废纸篓：

```bash
./zh-patch rollback
```

完整流程见 [`docs/INSTALL.zh-Hans.md`](docs/INSTALL.zh-Hans.md)。

---

## 语言资源

本工具不含任何中文文本。要安装任何东西，你必须自己制作一个包含消息的目录，
并且必须拥有使用这些文本的权利。

查看应用期望哪些 key：

```bash
./zh-patch keys --out my-catalog/base.json
```

这会写出全部必需的 key，值留空。它刻意**不**导出应用自带的英文文本——
需要知道某条消息是什么意思，请直接查看你本机已安装的应用。

然后写一份 `catalog.json` 清单、填好各条译文，把目录用 `--catalog-dir` 传进来。
格式、校验规则以及工具会检查什么，见
[`docs/CATALOG-FORMAT.md`](docs/CATALOG-FORMAT.md)；
起点模板在 [`templates/catalog/`](templates/catalog/)。

若语言资源格式错误、覆盖率不足，或会在界面上留下可见空洞，加载器会拒绝，
并逐个指出有问题的 key 供你修复。

要看到每一处问题的细节——包括应用对每条消息提供哪些参数、你的资源提供了哪些——
请用 `lint`：

```bash
./zh-patch lint --catalog-dir ~/my-catalog
./zh-patch lint --catalog-dir ~/my-catalog --report report.md
```

有一类情况是**放行**而非拒绝的，值得了解。当应用按数量或类别在不同参数之间做选择时，
不区分单复数或性数的语言会省略其中部分分支，只被该分支使用过的参数也随之消失。
这是正确的译文，因此**无需任何标志即可安装**；`lint` 会列出被放行的内容，
`apply` 会把数量记入安装标记文件。而应用在**所有分支之外**渲染的参数，
或落在译文**保留了的分支内**的参数，丢失就是可见空洞，一律拒绝。
**没有任何参数可以覆盖这一判断。**

> 自行提供语言资源并不会让你获得对它的任何授权，通过这些检查也不代表
> Anthropic 授权了什么。你所安装文本的责任由你自己承担。

---

## 会产生哪些变化

| | |
| --- | --- |
| 你已安装的应用 | 不变 |
| 用户数据、网关设置、切换工具 | 不变 |
| 新副本的签名 | **Ad-hoc**，取代 Anthropic 的 Developer ID |
| Gatekeeper | 会把该副本判定为 rejected（见下） |
| 钥匙串与原生功能 | **可能表现不同** |

### 签名与 entitlements

原构建携带若干 entitlements，它们只对"身份由配置文件背书"的代码才有意义——
`com.apple.application-identifier`、`com.apple.developer.team-identifier`，
以及绑定团队的 `keychain-access-groups`。ad-hoc 签名无法证明其中任何一个。
本工具会移除它们，并以 `com.apple.security.cs.disable-library-validation` 取代，
后者正是 ad-hoc 签名的 Electron 应用加载自身框架所需要的。

实际后果：

- **钥匙串**：应用存放在其团队作用域 keychain access groups 下的内容，
  副本已无法访问。请预期需要重新登录，也请预期副本与原版不共享已存凭据。
- **原生集成**：依赖代码签名的功能——部分权限、部分辅助程序、部分系统集成——可能不可用。
- **Gatekeeper**：副本未经公证、也没有 Developer ID 签名，因此 `spctl` 判定为拒绝。
  **由本工具在本机生成的**副本不带隔离属性，因而可以正常启动；
  而经过下载、打包或传输的副本会被打上隔离标记，Gatekeeper 会阻止它。

> 不要为了绕过这个问题而全局关闭系统完整性保护或 Gatekeeper。
> 那是为单个应用的便利而降低整个系统的安全性。如果本机生成的副本无法启动，
> 请反馈——见 [`docs/TROUBLESHOOTING.zh-Hans.md`](docs/TROUBLESHOOTING.zh-Hans.md)。

### 已验证环境

兼容性矩阵中的两个版本均在同一台 Mac 上验证，环境如下：

| | |
| --- | --- |
| macOS | 26.5.2 (25F84) |
| 架构 | Apple Silicon (arm64) |
| Claude Desktop | 2.26454.0、2.26454.2 |
| 系统完整性保护 | **验证机上为关闭状态** |
| 对副本的 Gatekeeper 评估 | `spctl` 报告 *rejected* |
| 副本来源 | 本机生成，因此未被隔离 |

两个版本均已验证：应用启动、简体中文语言选择器、中文界面与重启后语言保留。
在 2.26454.2 上，已有配置的 DeepSeek Gateway 还完成了两次请求并返回
“ok”。本工具**不会自动设置第三方网关**；钥匙串和原生集成功能尚未验证。

> **SIP 开启环境下的兼容性尚未确认。** 验证机上系统完整性保护（SIP）处于**关闭**状态，
> 而这不是 macOS 的默认配置。没有在任何开启 SIP 的 Mac 上测试过。
> 本工具不要求你关闭 SIP，你也不应该关闭它——但在 SIP 开启时结果能否工作，目前是未知的。

**未验证：**开启 SIP 的情况、Intel、其他 macOS 版本、上述两个固定版本之外的
Claude 构建、钥匙串、原生集成、应用之间的配置隔离及其他模型/网关的可靠性。
"在我测试的那台机器上能用"并不等于"在你的 Mac 上能用"。

---

## 命令

| 命令 | 用途 |
| --- | --- |
| `check` | 评估应用，可选评估语言资源。不写入任何内容。 |
| `apply` | 生成中文化的、已重签名的副本。 |
| `verify` | 复查已安装的副本。仅静态检查。 |
| `rollback` | 把已安装副本移到废纸篓。可逆。 |
| `lint` | 详细报告语言资源的每一处问题。不写入任何内容。 |
| `keys` | 列出应用期望的消息 key，值留空。 |
| `scan` | 静态扫描密钥与第三方材料。 |
| `version` | 工具版本与兼容性表。 |

任意命令加 `--json` 可得到机器可读输出。

退出码：`0` 成功，`1` 错误，`2` 用法错误，
`3` 应用版本不受支持，`4` 语言资源被拒，`5` 应用结构无法识别。

---

## 安全与隐私

- **离线。** 没有任何命令会发起网络请求。
- **无凭据。** 仓库中不含、也不索取任何 API key、令牌、cookie 或账号标识；
  工具从不读取它们。
- **不涉及用户数据。** 不读取也不写入 `~/Library/Application Support`。
- **不含第三方材料。** 仓库中没有应用二进制、没有改写过的 JavaScript、
  也没有提取出来的翻译目录。
- **已扫描。** `./zh-patch scan .` 会用仓库自带的扫描器扫描本仓库；
  测试套件断言结果为干净。

安全问题请见 [`docs/SECURITY.md`](docs/SECURITY.md)。

---

## 许可与商标

原创代码与文档：**Apache License 2.0** ——
见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE)。

该许可仅覆盖本项目自身的工作，不覆盖 Claude、Claude Desktop、
任何 Anthropic 资源或任何翻译。"Claude" 与 "Anthropic" 是 Anthropic PBC 的商标，
此处仅用于说明本工具与之互操作的对象，属描述性使用。
详见 [`docs/DISCLAIMER.md`](docs/DISCLAIMER.md)。

---

## 文档

| | |
| --- | --- |
| [安装指南](docs/INSTALL.zh-Hans.md) · [Install guide](docs/INSTALL.md) | 分步说明，含从备份安装 |
| [兼容性矩阵](docs/COMPATIBILITY.md) | 哪些构建可安装，以及验证一个新版本需要做什么 |
| [语言资源格式](docs/CATALOG-FORMAT.md) | 清单、schema、校验规则 |
| [故障排查](docs/TROUBLESHOOTING.zh-Hans.md) · [Troubleshooting](docs/TROUBLESHOOTING.md) | 出问题时怎么办 |
| [免责声明](docs/DISCLAIMER.md) | 完整的限制说明 |
| [安全](docs/SECURITY.md) | 扫描什么，以及如何反馈问题 |
| [贡献指南](CONTRIBUTING.md) | 含如何为新版本增加支持 |
| [更新日志](CHANGELOG.md) | 版本历史 |

English documentation: [`README.md`](README.md)。

---

## 参与贡献

为新应用版本增加支持意味着跑完整套验证流程并提交结果——检查项清单在
[`docs/COMPATIBILITY.md`](docs/COMPATIBILITY.md)。修掉语言资源里丢失的格式占位符
是很好的第一个贡献。见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
