# Figma 采集指南

## 能力探测

先列出当前宿主实际可用的 Figma 工具；不能假定某个 MCP 服务已经安装或登录。不同服务返回结构不同，必须检查响应，不要直接把摘要当 REST JSON。

本会话中 open-figma-mcp 的只读工具可作为适配示例：

| 目的 | 工具示例 |
|---|---|
| 连接与当前文档 | `figma_status`, `figma_get_metadata` |
| 当前选区 | `figma_get_selection` |
| 节点/子树 | `figma_get_node`, `figma_get_design_context` |
| 样式与变量 | `figma_get_styles`, `figma_get_variable_defs` |
| 组件 | `figma_get_local_components` |
| 字体 | `figma_get_fonts` |
| 原型 | `figma_get_reactions` |
| 参考图/资源导出 | `figma_get_screenshot`, `figma_save_screenshots` |

这些工具名称仅供查找；其他 MCP 服务使用其自身对应工具。工具声明的深度限制可能截断后代，必须补取。当前页面不一定是 URL 所指文件：核对文件和节点；无法核对时明确说明。

## 采集范围

只读取用户指定画板及实现必需的组件、变量、资源和交互目标。不要为了一个页面导出整个私有文件。截图和节点树均需保留，截图用于核对而不是替代结构。记录缺失的样式、变量绑定、字体和目标画板。

将 MCP 响应适配为 CLI 支持的 REST 节点结构或 capture 格式，详见 `input-contract.md`。不要把任意 MCP 文本直接输入生成器并声称已完成解析。保留原始响应便于追溯，生成前对照节点 ID、尺寸和文本。

布局采集同时保留父子节点的 `absoluteBoundingBox` 和子节点的 `constraints.horizontal` / `constraints.vertical`。约束是相对直接父节点的规则，不可用画板尺寸替代嵌套父节点尺寸。缺失约束不应根据截图猜测；Figma `constraints` 与 `layoutMode`、hug/fill、padding、spacing 是不同字段，不能互相代替。

## URL/离线回退

URL 只提供 file key/node id。只有有授权的数据读取渠道时才能获取设计。CLI 本身不下载 URL；无访问权限时要求用户提供 Figma REST file/nodes 响应，或 documented capture JSON 与本地资源。Figma 没有通用的“导出页面为 REST JSON”菜单，不要给出不存在的菜单指令。

不得将 token 写入 capture、Swift、日志或示例。下载/导出仅针对已确认的资源，写入约定目录；避免未经核对的跳转与任意 URL。SVG 原稿可保留，但运行时优先 PNG/PDF；没有转换工具时报告缺失，不要伪造成功。

采集基础 flow 时须显式取得 primaryAxisSizingMode、counterAxisSizingMode（不可把缺失当 FIXED）、四边 padding、两轴 alignment、itemSpacing、layoutWrap，以及所有节点的 layoutSizingHorizontal/Vertical、layoutGrow、layoutAlign、layoutPositioning、min/max width/height、strokesIncludedInLayout 和 itemReverseZIndex。不要只采父 frame；叶子父向字段同样重要。旧无版本 layout 丢失证据需重采，不扩展旧顶部 padding。无字段不猜截图语义；unsupported 字段保留并整组回退。
