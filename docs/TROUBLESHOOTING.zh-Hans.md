# 故障排查

按现象查找，运行诊断命令，再看结论。

---

## 工具拒绝安装

多数情况下这是正确行为。每次拒绝都会说明原因。

### 退出码 3 —— 版本不受支持

```
error: Claude Desktop 2.26454.2 is not a supported version.
```

你安装的版本尚未经过验证。这不是你的环境有问题。请改为从受支持版本的副本安装，
见[从备份安装](INSTALL.zh-Hans.md#从备份安装)。

**不要**通过修改 `Info.plist` 里的版本号来绕过。结构与摘要校验会拒绝该结果；
即便没有拒绝，你安装的也是一个未经测试的组合。

### 退出码 4 —— 语言资源被拒

输出会指出有问题的具体 key。要看完整信息——每一处结论、原因，以及两边的参数集合——
请用 `lint`：

```bash
./zh-patch lint --catalog-dir ~/my-catalog
./zh-patch lint --catalog-dir ~/my-catalog --report report.md
```

常见原因：

| 提示 | 含义 |
| --- | --- |
| `base coverage is N%, below the required 70%` | 语言资源覆盖的 key 太少。 |
| `drops a format argument the application's message provides` | 应用在所有分支之外、或在你**保留**的分支内渲染的占位符丢失了。请修改译文。 |
| `uses a format argument the application's message does not provide` | 译文凭空多了一个占位符。格式化时会抛错。 |
| `unsupported argument type` | 某条消息不是合法的 ICU MessageFormat。 |
| `remove a plural or select branch …accepted` | 这是警告而非错误，无需处理，见下。 |
| `does not exist in this application build` | 这是警告而非错误：该 key 会被写入但不会被使用。 |
| `no language resource was supplied` | 没有传 `--catalog-dir`。 |

对于占位符丢失，修复点在语言资源本身：应用原文是 `saved {fileName}`，
译文里就必须同样包含 `{fileName}`。详见
[格式占位符说明](CATALOG-FORMAT.md#why-format-arguments-are-checked)。

**没有任何参数可以覆盖拒绝。** 出现错误意味着界面会确实丢失信息，
正确的做法是修好那条消息，而不是强行安装。

### "remove a plural or select branch … accepted"

这是警告，不需要你做任何事。该消息省略了应用具有的某个分支，
连同只被该分支使用的参数一起。不区分单复数/性数的语言本来就这样写，
因此**无需任何标志即可安装**。数量会被记入安装标记文件，`verify` 会把它报告回来，
所以这次放行是可见的，而不是悄悄发生的。

想知道具体是哪些消息、哪些参数，运行 `lint` 即可。

### 退出码 5 —— 应用结构与预期不符

该构建不具备本工具认识的目录结构。通常意味着版本号与文件内容不一致，
或者该应用已经被修改过。

诊断：

```bash
./zh-patch check --app /path/to/Claude.app
```

### `target already exists`

```bash
./zh-patch rollback --target /Applications/Claude-3P-ZH.app
```

或者换一个 `--target`。工具不会覆盖已有目录，因为那个目录可能正是你唯一能用的副本。

### `the source bundle's signature does not verify`

待处理的源应用已损坏或被修改。请恢复一份干净的应用副本。
不要对一个连自身完整性校验都通不过的应用打补丁。

---

## 副本无法启动

### 第一步：检查是否被隔离

```bash
xattr -l /Applications/Claude-3P-ZH.app
```

如果输出里出现 `com.apple.quarantine`，说明该副本经过下载、打包或传输，
因而被打上了隔离标记。由本工具**在本机直接生成**的副本不会有这个标记。

被隔离副本的正确处理方式是：在本机重新生成，而不是传输它。
**不要**执行 `xattr -d`、`spctl --master-disable` 或全局关闭 Gatekeeper。
如果本机生成的副本仍被隔离，那值得作为问题反馈。

### 第二步：检查签名

```bash
codesign --verify --deep --strict --verbose=2 /Applications/Claude-3P-ZH.app
```

预期输出 `valid on disk` 与 `satisfies its Designated Requirement`。
其他任何输出都说明副本已损坏，删除后重新安装。

### 第三步：从终端启动

从终端启动可以看出访达只会提示"无法打开"的那个真正错误：

```bash
/Applications/Claude-3P-ZH.app/Contents/MacOS/Claude
```

记下输出内容，然后关闭它。

### 第四步：确认原版仍可运行

```bash
open -a /Applications/Claude.app
```

如果原版也启动不了，那问题不在本工具。

---

## 界面仍然是英文

1. **检查设置项。** Settings → Language，选择 Chinese (Simplified)。
   副本本身不会自动修改你已保存的语言偏好。
2. **确认语言资源确实装进去了。**

   ```bash
   ./zh-patch verify --target /Applications/Claude-3P-ZH.app
   ```

   每个语言文件都应显示 `ok`，`catalog digest` 应显示 `matches marker`。

3. **确认选择器已被改写。**

   ```bash
   grep -c 'zh-Hans' /Applications/Claude-3P-ZH.app/Contents/Resources/ion-dist/assets/v1/c49da61a8-BM3hC-jO.js
   ```

   结果为 0 说明改写没有生效。

### 语言列表里根本没有这一项

请就此停下，不要去改配置文件。在别处强行写入该值既不能解释选择器为何缺少这一项，
还会掩盖真正的故障点。

请收集以下信息：

```bash
./zh-patch verify --target /Applications/Claude-3P-ZH.app > report.txt 2>&1
./zh-patch version >> report.txt
sw_vers >> report.txt
uname -m >> report.txt
csrutil status >> report.txt
codesign -dv --verbose=4 /Applications/Claude-3P-ZH.app >> report.txt 2>&1
```

然后把这个文件作为附件提交 issue。它不包含任何凭据、个人信息，
也不包含你的语言资源。

### 部分文案是英文，部分是中文

这在某种程度上是预期内的。语言资源与应用是分开版本化的，
因此语言资源里没有的 key 会回退到英文。`check` 会报告覆盖率；
覆盖率不足 100% 就会在你没有覆盖到的地方显示为中英混杂。

如果某个**具体**控件读起来不对劲——比如一句话里本该有名称的位置是空的——
那就是格式占位符丢失，见
[格式占位符说明](CATALOG-FORMAT.md#why-format-arguments-are-checked)。

---

## 登录失败，或副本重新要求输入凭据

这是预期行为，[`DISCLAIMER.md`](DISCLAIMER.md) 中有说明。ad-hoc 签名无法携带原版
构建所拥有的、绑定团队的 keychain access groups，因此副本访问不到存放其中的凭据。
请把副本当作一个在存储密钥方面独立的另一个应用来看待。

---

## 某功能在原版可用，在副本里不可用

部分能力依赖于代码签名。请先记录是哪个功能，再确认它在原版里是否正常——
如果两边都失败，那就与本工具无关。

除非你能证明是本工具的改动导致，否则请把它作为**已知限制**而非 bug 反馈。
无论哪种，这都是有价值的信息；免责声明之所以把这些列为"未验证"，
正是因为还没有人逐项测过。

---

## 网关或切换工具失效了

本工具不读取也不写入你的网关或切换工具配置，也不触碰用户数据。
如果某项设置看起来丢了，请先确认你改的是哪个应用：两个副本共用用户数据，
但它们是彼此独立的 bundle，很容易在配置一个的时候看着另一个。

用切回原版来定位：

```bash
osascript -e 'quit app "Claude"'
open -a /Applications/Claude.app
```

如果问题依然存在，那就不是本工具造成的。

---

## 回退

```bash
./zh-patch rollback --target /Applications/Claude-3P-ZH.app
```

如果被拒绝并提示 `no install marker`，说明该 bundle 不是本工具的产物，
因此被刻意保留不动。如果你确实知道那是什么，可以自行删除。

副本会被移到废纸篓，所以不会真正销毁任何东西。
`~/Library/Application Support` 下的用户数据不受影响，
回退时不要把它一并删除。

---

## 反馈问题

请附上：

- `./zh-patch version` 的输出；
- `./zh-patch check` 的输出，以及（如果走到那一步）`./zh-patch verify` 的输出；
- `sw_vers` 与 `uname -m`；
- `csrutil status` —— 验证机上 SIP 是关闭的，所以这一项很重要；
- 你预期发生什么，实际发生了什么。

请**不要**附带你的语言资源、应用副本，或任何含凭据与聊天内容的东西。
上面那份报告文件已经足够。
