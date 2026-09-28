# 输入契约

权威示例和字段说明见 [examples/README.md](../examples/README.md)；正式中间表示见 [figma-ir.schema.json](../schemas/figma-ir.schema.json)。以当前 CLI `--help` 和示例实际字段为准。

## 三种输入路径

1. **Figma MCP**：由宿主助手读取节点、样式、变量、原型和图片，然后适配为示例 capture 格式。CLI 不直接调用 MCP，也不接受所有服务的任意原始响应。
2. **Figma URL**：由宿主助手定位授权可读的文件/节点后走 MCP 采集；无数据渠道时请求 JSON。离线 CLI 不把 URL 当设计数据，不执行下载。
3. **本地 JSON**：支持生成器文档列出的 Figma REST 节点/文件响应或 capture 格式。图片在指定本地资源根目录下；不能引用任意系统路径。

## 多画板与输出清单

生成器递归穿过 `DOCUMENT`、`CANVAS`、`SECTION` 容器，把遇到的第一层非容器节点作为独立页面；页面内部的嵌套 frame 保留为子视图，不再次拆页。单独节点输入生成一对 Controller/RootView，空容器不生成虚构页面。

`manifest.json` 的 `screens` 按页面遍历顺序记录 `node_id`、`controller`、`view`，文件名是相对输出目录的 Swift 文件名。同名、仅大小写不同或中文名称会经过稳定消歧，应读取清单而不是自行推测文件名。共享颜色常量、交互类型和资源只输出一份；跨页面目标存在于采集范围中不代表导航已经接线。

所有模板渲染、资源规划与输出冲突预检查都在写出之前完成。预检查避免已知冲突导致部分输出，但不是文件系统事务，不能承诺在磁盘错误或并发修改时自动回滚。

## IR 验证与失败行为

`validate` 检查节点、bounds、样式、文本、资源、交互、诊断及已出现值集合的字段类型，并用 `$.root.children[0]...` 这样的路径定位错误。数字不接受布尔值、非有限值或不能表示为有限浮点数的值；父子坐标相减溢出也会被拒绝。归一化 IR 的颜色必须是 `#RRGGBB` / `#RRGGBBAA` 字符串，而非 capture 中的 RGB 对象。

节点必须包含 `children` 数组；`name` 可省略，输入框占位文本回退为 `Input`。`tokens` 可省略，但一旦提供须包含 version/colors/fonts/spacing/radii；这仍只是已出现值集合，不表示变量解析已经实现。顶层交互记录必须带非空 `source`。合法的 error 级诊断同样阻止生成。

无效 IR 在读取模板、打包资源或创建输出目录之前被拒绝。`validate` CLI 输出 JSON 检查结果并以非零状态退出；`generate` 的预期输入/文件错误输出简短 stderr，而非 Python traceback。这些检查不是完整 JSON Schema 引擎，也不覆盖任意深度树、原始 capture 的所有畸形结构或 iOS 运行时正确性。

## 基础响应式 constraints

capture 节点可提供 `"constraints": {"horizontal": "STRETCH", "vertical": "MAX"}`，归一化 IR 保留同名对象。每轴支持 `MIN`、`MAX`、`CENTER`、`STRETCH`、`SCALE`，缺失轴按 `MIN` 处理；无 constraints 继续使用原固定几何输出。字段必须是对象、轴值必须是支持的大写字符串，不接受未知键或根据节点名称推断规则。

- `MIN`：固定起点偏移与尺寸。
- `MAX`：固定终点边距与尺寸。
- `CENTER`：固定相对父节点中心的偏移与尺寸。
- `STRETCH`：固定两侧边距，不再同时固定该轴尺寸。
- `SCALE`：以直接父节点的采集尺寸计算位置和尺寸比例；父节点该轴尺寸为零时报告诊断，回退该轴固定 `MIN` 几何。

生成页面的根视图没有可用于上述映射的父节点；其 constraints 不参与页面内部约束生成。比例、中心偏移和边距等派生几何必须仍是有限数。生成器用 leading/trailing 和 top/bottom 表达边界；SCALE 使用辅助 UILayoutGuide 表达比例位置，负偏移通过反向端点表达。

基础 constraints 不是 Figma Auto Layout；下述独立 layout v1 支持固定尺寸 flow，但不实现 hug/fill 或字体自适应。尺寸过小导致的 STRETCH 冲突、RTL、safe area 与实际运行时布局仍须目标项目验收。示例见 `examples/responsive-input.json`。

## 使用原则

- `normalize` 处理源数据，产出 `figma-uikit-ir/1`。
- `validate` 对支持的运行时结构与引用做检查，不等价于通用 JSON Schema 引擎或 iOS 编译器。
- `generate` 消费 IR，生成 Swift、资源和诊断；输入和选项一致应产生相同输出。
- `test` 运行仓库测试。

```bash
python3 /absolute/path/figma-to-uikit/scripts/figma_to_uikit.py --help
python3 /absolute/path/figma-to-uikit/scripts/figma_to_uikit.py normalize --help
python3 /absolute/path/figma-to-uikit/scripts/figma_to_uikit.py generate --help
python3 /absolute/path/figma-to-uikit/scripts/figma_to_uikit.py validate --help
```

不要在 capture 中保存访问 token、签名下载 URL 或与所选画板无关的数据。保留源节点 ID，保留视觉子节点顺序，明确缺失与不支持的字段。输出可读代码不是对完整 Figma 功能的承诺；复杂布局、字体、动画、业务导航需要后续适配和验证。


## Versioned fixed-size flow (layout v1)

Top-level IR remains `figma-uikit-ir/1`. Only captures containing container layout fields receive `layout.version: 1`; captures without layout evidence retain their original legacy bytes. Capture mapping:

- `layoutMode` → `mode` (default NONE; unknown strings warn and fall back).
- `paddingTop/Right/Bottom/Left` → `padding.top/right/bottom/left` (default 0 each).
- `itemSpacing` → `item_spacing` (default 0).
- `primaryAxisAlignItems/counterAxisAlignItems` → `primary_align/counter_align` (default MIN).
- `primaryAxisSizingMode/counterAxisSizingMode` → `primary_sizing/counter_sizing` (default UNKNOWN, never inferred FIXED).
- `layoutWrap` → `wrap` (default NO_WRAP); `strokesIncludedInLayout/itemReverseZIndex` → `stroke_inclusive/reverse_stacking` (default false).

Parent-facing evidence is a separate `layout_item.version: 1`: `layoutSizingHorizontal/Vertical` → `horizontal_sizing/vertical_sizing`, `layoutGrow` → `grow`, `layoutAlign` → `align`, `layoutPositioning` → `positioning`, and `minWidth/maxWidth/minHeight/maxHeight` → snake_case. Absent item fields mean captured fixed geometry, no grow/stretch/absolute positioning or min/max limits; absent container sizing remains UNKNOWN. Legacy and modern sizing signals are both retained and checked. The schema lists accepted enums. Unknown local versions/keys, malformed types, booleans as numbers, NaN/Infinity and arithmetic overflow are rejected before generation writes or reads templates/assets. Finite negative spacing is valid but unsupported; padding and limits must be nonnegative. Validation does not mutate IR.

Supported containers are FRAME/COMPONENT/INSTANCE, including generated screen roots: HORIZONTAL/VERTICAL, explicit FIXED primary and counter sizing, no wrap, fixed child bounds, MIN/CENTER/MAX on both axes. Sibling anchors preserve order, fixed dimensions and gap; asymmetric padding shifts center by half the padding difference. Container geometry remains controlled by its parent, existing constraints or host root size. No root fixed-size constraints or UIStackView are inserted. Oversized children may overflow rather than compress or wrap.

Any unsupported direct child or container signal causes **all direct children** to use the original constraints/geometry branch: AUTO/HUG/FILL, grow/stretch, conflicting sizing, SPACE_BETWEEN/baseline/wrap, negative spacing, hidden or absolute children, min/max sizes, stroke inclusion, reverse stacking, unsupported container type or unknown mode. Diagnostics name the container, affected node and field; normalization, validation and manifest share stable deduplicated warnings. Descendant containers decide independently. Own parent-facing positioning/grow/align does not disable a container's internal flow.

Legacy unversioned HORIZONTAL/VERTICAL layout is insufficient evidence: recapture, do not expand legacy scalar padding to all four sides. Missing layout and NONE preserve geometry behavior. Supported flow overrides ordinary child constraints, but their syntax is always checked; derived constraint arithmetic is checked only on the selected rendering branch. Text, assets, styles and interaction scaffolds are unchanged; this is not text intrinsic-size solving.
