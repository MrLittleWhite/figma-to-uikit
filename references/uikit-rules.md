# UIKit 实现规则

## 布局与组件

- 默认使用 UIKit + Swift + 原生 Auto Layout，优先复用目标项目已有组件。
- UILabel 承载静态文字；混合字体/行距须按证据生成 NSAttributedString，不能声称普通 label 保留全部 rich text。
- 按钮、输入框、滚动容器需显式语义/override；仅名字包含 Button 不能保证它就是 UIButton。
- 自由布局保留相对父节点坐标；Figma absoluteBoundingBox 是画布坐标，转换时减去父节点原点。
- Auto Layout 的 hug/fill/fixed、padding、spacing、alignment、绝对定位子节点与 UIStackView 并非一一等价。无法完整映射时保留几何回退并报告，不要制造过约束。
- UIScrollView 使用 contentLayoutGuide/frameLayoutGuide。动态列表需要数据源；静态重复卡片不自动变成带虚构数据的 UICollectionView。
- safe area 必须按设计/现有项目明确处理。不要同时将同一内容固定到画布和 safe area。
- 约束语法正确不代表无歧义；需要模拟器运行时验证。

### 基础 constraints 与 Auto Layout 的区别

Figma 子节点的 `constraints.horizontal` / `constraints.vertical` 分别描述直接父节点尺寸改变时的行为：`MIN` 固定起点和尺寸，`MAX` 固定终点边距和尺寸，`CENTER` 固定中心偏移和尺寸，`STRETCH` 固定两侧边距，`SCALE` 保持位置和尺寸占父节点的比例。不要用整个画板的尺寸计算嵌套节点比例。

这些规则不等于 Figma Auto Layout：hug/fill、文本自适应和滚动容器仍需单独适配；有明确 layout v1 证据时支持固定 flow 的 spacing/padding。过小的父容器可能让 STRETCH 推导出负尺寸，需在目标项目定义最小尺寸或断点；不能仅凭生成约束通过类型检查就认定任意屏宽可用。SCALE 只缩放节点几何，不自动缩放字体、圆角和图像导出分辨率。水平 leading/trailing 约束还受布局方向影响；物理坐标设计须额外核对 RTL，不能宣称已经完成 RTL 适配。

## 令牌与样式

- 只提取有来源的令牌，保留 node ID / 原名追溯。
- 变量 alias 需要处理缺失引用和循环；模式名不一定是 light/dark，不可臆断。
- 字体必须检查实际可用性；Figma family/style 不总是 UIFont PostScript 名称。
- 颜色注意 alpha，圆角、阴影和边框注意 clipping；mask、渐变、多重 paint 和复杂 blend 不支持时明确报告。
- 无证据不增加暗色主题；无支持不宣称多模式变量已实现。

## 资源与交互

- 图片资产记录 node ID、导出尺寸和 scale。UIImageView 不直接加载任意 SVG。
- 单色图标才可能用 template rendering；多彩图不默认着色。
- 原型 tap 可产生 callback/router 请求，但实际 push/present/back 依赖目标项目。
- 缺失 destination、hover/drag、变量条件、复杂动画是未实现能力，不能变成无日志 no-op。
- 外部 URL 行为由应用审核和显式实现，不因设计稿含链接就自动打开。

## 可访问性与验收

适配时考虑 accessibilityLabel、Dynamic Type、多行截断、44pt 可点击区域、本地化和 RTL。若与固定尺寸视觉稿冲突，解释取舍。记录 iOS SDK 编译、模拟器截图、运行时约束告警和实际交互检查；未运行的项目单独列出。避免“支持 UIKit 所以一定可编译”一类推断。

固定 flow 使用兄弟原生 anchors，不使用 UIStackView。首项按 MIN/CENTER/MAX 定位，不同时强迫末项贴两端；交叉轴 center 修正非对称 padding。容器全部直接子项统一支持或回退，后代独立判定。详见 input-contract 的 versioned flow。
