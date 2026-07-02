本页面详细阐述植被指数智能分析平台中遥感影像的上传流程、波段映射机制与元数据推断逻辑。系统通过前后端协作，实现了从文件选择到批量任务提交的完整工作流，其中智能元数据推断和波段映射是确保后续分析准确性的关键环节。

## 影像上传流程与前后端协作

影像上传功能由前端 `AssetToolbar.vue` 组件和后端 `/api/assets/upload` 端点协同完成。前端采用 `XMLHttpRequest` 实现实时上传进度监控，支持文件选择器和拖拽两种交互方式。

前端上传流程从文件选择开始，通过 `openPicker` 函数触发隐藏的文件输入框。当用户选择文件后，`onFileChange` 函数会调用 `uploadFiles` 进行批量处理。该函数首先过滤出 `.tif` 或 `.tiff` 文件，然后串行上传每个文件。在上传过程中，前端通过 `uploadForm` 函数中的 `xhr.upload.onprogress` 事件监听器实时更新进度百分比，并维护上传阶段状态（从 `uploading` 到 `pyramid` 再到 `preview`）。

Sources: [AssetToolbar.vue](frontend/src/components/AssetToolbar.vue#L93-L149)

后端接收到上传文件后，`save_uploaded_asset` 函数执行以下关键步骤：首先验证文件后缀是否为 `.tif` 或 `.tiff`，然后生成安全的文件名（UUID + 原后缀），将文件保存到 `data_dir/inputs` 目录。保存完成后，系统立即执行三个关键操作：确保影像金字塔（overview）存在、提取元数据、生成预览图像。这些操作确保了影像在后续处理中的性能和可访问性。

Sources: [assets.py](backend/app/services/assets.py#L285-L310)

## 元数据推断机制与传感器识别

元数据推断是波段映射的基础，系统通过 `inspect_raster` 函数实现多层次的元数据提取。该函数首先读取影像的基本信息：尺寸（宽度、高度）、波段数、数据类型、坐标参考系（CRS）、边界范围和分辨率。

在波段元数据提取方面，系统采用**三级推断策略**：首先尝试从GeoTIFF文件的波段描述（`dataset.descriptions`）和标签（`dataset.tags`）中提取波长信息，通过正则表达式匹配纳米（nm）或微米（µm）单位的数值。如果直接提取失败，系统会尝试通过文件名模式匹配已知传感器的波段配置。

Sources: [assets.py](backend/app/services/assets.py#L133-L180)

系统内置了四个常见遥感传感器的波段配置文件：GF-1（4波段）、Landsat 8/9 OLI（7波段，支持LAD08和LAD09两种命名）、Sentinel-2A/2B MSI（4波段，SHB02前缀）。`_sensor_band_profile` 函数通过正则表达式匹配文件名前缀，同时验证波段数量是否匹配，确保推断的准确性。当匹配成功时，系统会为每个波段自动填充标准波长值和描述信息。

Sources: [assets.py](backend/app/services/assets.py#L19-L70)

## 波段映射系统：自动推断与手动调整

波段映射是将影像的物理波段映射到逻辑波段（如红、绿、蓝、近红外等）的关键过程，直接影响植被指数计算的准确性。系统采用**前端推断、后端验证**的架构设计。

前端的波段映射推断由 `inferBandMapping` 函数实现，该函数采用**三重匹配策略**：首先尝试波长匹配，将波段波长与标准逻辑波段的波长范围进行最近邻匹配。例如，近红外（NIR）的波长范围为760-900nm。如果波长匹配失败，系统会尝试描述匹配，通过正则表达式检测波段描述中的关键词（如 "blue"、"nir"、"swir1"）。最后，如果以上两种方法都失败，系统会使用基于波段数量的兜底映射，假设影像遵循常见的多光谱顺序。

Sources: [workspace.ts](frontend/src/stores/workspace.ts#L31-L78)

前端还提供了波段映射的验证和手动调整界面。`bandValidation` 计算属性会检查映射的有效性，包括重复映射、超出源影像范围的映射，以及关键波段（如红和近红外）是否已映射。用户可以通过波段映射弹窗查看每个源波段的详细信息（波长、描述），并手动调整映射关系。

Sources: [workspace.ts](frontend/src/stores/workspace.ts#L139-L160)

## 影像金字塔与预览生成

为优化大规模影像的浏览和瓦片渲染性能，系统在上传时自动构建影像金字塔（overview）。`ensure_raster_overviews` 函数首先计算所需的金字塔层级，直到最长边接近256像素。系统采用2倍的下采样因子，最大支持128倍下采样。

金字塔构建采用惰性策略：如果影像已存在金字塔，则直接复用；如果影像尺寸较小（最长边≤512像素），则无需构建；否则，系统会使用DEFLATE压缩和平均重采样方法在GeoTIFF文件内部构建金字塔。构建完成后，系统会添加标签记录构建参数，便于后续识别金字塔的来源。

Sources: [assets.py](backend/app/services/assets.py#L81-L121)

预览图像生成由 `write_asset_preview` 函数完成，该函数创建一个缩放后的PNG图像，用于前端快速显示。对于多波段影像，系统默认使用波段3、2、1作为RGB通道；对于单波段影像，则创建灰度预览。预览图像采用2-98百分位拉伸和Alpha通道处理，确保在前端地图上的可视化效果。

Sources: [assets.py](backend/app/services/assets.py#L205-L235)

## 批量处理与任务提交

上传完成后，用户可以通过波段映射确认后提交批量处理任务。前端的 `submitBatch` 函数会遍历上传队列中的所有影像，为每个影像调用 `executeAssetBatch` 提交异步任务。

`executeAssetBatch` 函数通过OGC API - Processes规范提交任务，请求体包含影像路径、波段映射、索引列表、引擎选择和任务优先级等参数。系统采用异步任务模式（通过 `Prefer: respond-async` 头指定），允许后端在后台处理计算密集型操作，同时前端可以继续其他工作。

Sources: [usePlatformApi.ts](frontend/src/composables/usePlatformApi.ts#L136-L159)

后端的任务提交接口遵循严格的验证规则：索引列表长度限制在1-35之间，波段映射必须包含有效的键值对，引擎选择必须来自预定义选项（auto、numpy、joblib、torch），块大小限制在128-2048之间。这些约束确保了任务参数的合法性和系统的稳定性。

Sources: [schemas.py](backend/app/api/schemas.py#L31-L43)

## 错误处理与数据验证

系统建立了多层错误处理机制，确保用户获得清晰的反馈。在文件上传阶段，后端验证文件后缀、文件存在性和存储空间。元数据提取阶段验证文件格式的完整性和波段信息的可读性。波段映射阶段验证映射关系的有效性和完整性。

前端通过 `bandValidation` 计算属性提供实时验证反馈，包括三种错误类型：重复映射（同一源波段被映射到多个逻辑波段）、范围错误（映射的波段号超出源影像实际波段数）、关键缺失（必需的红、近红外波段未映射）。这些验证确保了后续植被指数计算的数据质量。

Sources: [workspace.ts](frontend/src/stores/workspace.ts#L139-L160)

## 数据结构与API端点

系统定义了清晰的数据结构来保证前后端契约的一致性。`UploadedAsset` 接口描述了上传资产的完整信息，包括对象键、本地路径、文件名、大小、元数据、预览路径等。`RasterMetadata` 接口包含了影像的所有空间和波段元数据，是波段映射和后续处理的基础。

关键API端点包括：
- `POST /api/assets/upload`：处理GeoTIFF文件上传，返回完整的资产信息和元数据
- `POST /api/assets/inspect`：检查已存在影像的元数据，用于本地文件或已上传资产的元数据查询
- `POST /api/assets/upload-url`：生成MinIO预签名上传URL，用于大文件分片上传
- `POST /processes/{process_id}/execution`：执行OGC兼容的处理任务，支持同步和异步模式

Sources: [platform.ts](frontend/src/types/platform.ts#L7-L40)

## 配置与存储架构

系统配置通过环境变量集中管理，使用 `VIP_` 前缀区分。数据目录默认为 `data`，所有上传的影像保存在 `data/inputs` 子目录，预览图像保存在 `data/previews` 子目录。系统支持可选的MinIO对象存储，通过 `minio_enabled` 配置控制是否启用。当MinIO启用时，影像会同步上传到对象存储；否则，系统使用本地文件系统存储。

Sources: [settings.py](backend/app/settings.py#L14-L43)

## Next Steps

完成遥感影像上传与波段映射后，建议继续阅读以下相关页面：
- [GeoTIFF 动态瓦片叠加与图层控制](20-geotiff-dong-tai-wa-pian-die-jia-yu-tu-ceng-kong-zhi) - 了解如何在地图上可视化已上传的影像
- [统计图表与多指数结果切换](22-tong-ji-tu-biao-yu-duo-zhi-shu-jie-guo-qie-huan) - 学习如何分析计算结果并创建可视化图表
- [统一公式注册表与指数定义](7-tong-gong-shi-zhu-ce-biao-yu-zhi-shu-ding-yi) - 深入理解波段映射如何应用于植被指数计算