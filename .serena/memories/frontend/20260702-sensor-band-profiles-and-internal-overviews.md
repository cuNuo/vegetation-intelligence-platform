# 传感器波段配置与测试影像内部 overviews

## 一句话结论

- `data/test` 四个 GeoTIFF 已具备内部 DEFLATE overviews，`GF01/LAD08/LAD09/SHB02` 可依据本项目原始数据恢复正确波段，不依赖 `.enp`。

## 适用场景

- 维护影像上传、元数据检查、内部金字塔、波段自动映射或这三类课程数据时读取。
- 用户询问 Landsat 第 1 波段、GF-1 或 Sentinel-2 导出 TIF 波段顺序时读取。

## 首选入口

- 路径：`backend/app/services/assets.py`
- 关键文件：`backend/tests/test_assets.py`、`frontend/src/stores/workspace.ts`、`frontend/src/components/AssetToolbar.vue`
- 推荐起点：先看 `_SENSOR_BAND_PROFILES` 和 `inspect_raster()`，再看前端 `inferBandMappingByWavelength()`。

## 稳定约束 / 正确做法

- TIF 自带描述和波长始终优先；文件名前缀配置只能补空缺。
- `GF01` 4 波段：Blue B1=485 nm、Green B2=555 nm、Red B3=660 nm、NIR B4=830 nm。
- `LAD08/LAD09` 7 波段：Coastal Aerosol B1=443 nm、Blue B2=482 nm、Green B3=561 nm、Red B4=655 nm、NIR B5=865 nm、SWIR1 B6=1610 nm、SWIR2 B7=2200 nm。
- `SHB02` 4 波段：Sentinel-2 B02/B03/B04/B08，即 Blue/Green/Red/NIR。
- 文件名前缀与预期波段数必须同时匹配，未知影像继续走原有兜底。
- overview 只用于预览和瓦片读取，不改变全分辨率指数计算。

## 常见误区

- Landsat B1 是 Coastal Aerosol，不是平台逻辑 Blue；Blue 应映射源波段 2。
- `LAD08` 月度产品的原始目录同时包含 Landsat 8 和 9，不能只标记为 Landsat 8。
- `.enp` 是 ENVI 专用旁车金字塔，不能作为 Rasterio/GDAL 通用 overview。
- 不要因为影像有 4 或 7 个波段就直接判定传感器，必须同时检查文件名前缀。

## 关联 evidence

- `.evidence/active/20260702-1901-测试影像内部概览与传感器波段识别.md`
- `.evidence/runtime-logs/20260702-内部概览批量构建.log`

## 相关路由 / 文档

- `README.md`
- `docs/superpowers/specs/2026-07-02-sensor-band-overview-design.md`

## overview 结果

- `bajiepart1.tif`：`[2, 4, 8, 16, 32]`
- `GF01_130200_202301.tif`：`[2, 4, 8, 16, 32, 64]`
- `LAD08_130200_202301.tif`：`[2, 4, 8, 16, 32, 64]`
- `SHB02_130200_202301.tif`：`[2, 4, 8, 16, 32, 64, 128]`

## 最后验证

- 时间：2026-07-02 19:18
- 验证人 / 来源：Codex；本地 E:\课设 原始数据、Ruff、pytest、Vite build 和真实 TIF 回读。
- 结果：Ruff 通过；后端 38 passed；前端构建通过；四个 TIF 二次检查均返回 `reused`。