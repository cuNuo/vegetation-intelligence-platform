<!-- frontend/src/components/MapWorkspace.vue -->
<!-- 文件说明：MapLibre 遥感地图工作区。 -->
<!-- 主要职责：管理底图、源影像、结果瓦片、范围定位、图层顺序和对比模式。 -->
<!-- 对外约定：asset/product props 与 locate 等事件。 -->
<!-- 依赖边界：地图命令仅在 style ready 后执行。 -->

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, shallowRef, useTemplateRef, watch } from 'vue'
import maplibregl, { type Map } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Product, UploadedAsset } from '@/types/platform'

const props = defineProps<{
  asset: UploadedAsset | null
  product: Product | null
  products?: Product[]
  activeProductIndex?: number
}>()

const emit = defineEmits<{
  selectProduct: [index: number]
}>()

type BasemapKey = 'vector' | 'image' | 'terrain'
type CompareMode = 'before' | 'after' | 'both'

const mapContainer = useTemplateRef<HTMLDivElement>('mapContainer')
const map = shallowRef<Map | null>(null)
let resizeObserver: ResizeObserver | undefined
let mapReady = false
const opacity = defineModel<number>('opacity', { default: 0.78 })
const cursorCoordinates = shallowRef('将鼠标移入地图读取坐标')
const activeBasemap = shallowRef<BasemapKey>('image')
const compareMode = shallowRef<CompareMode>('both')
const sourceTilesInView = shallowRef(false)
const sourceTilesReady = shallowRef(false)
const resultTilesInView = shallowRef(false)
const mapBearing = shallowRef(0)
const seenSourceKeys = new Set<string>()
let pendingSourceLocateKey = ''
let renderedSourceSignature = ''
let renderedProductSignature = ''
const layerState = reactive({
  basemap: true,
  sourcePreview: true,
  footprint: true,
  result: true,
})
const TIANDITU_TOKEN = import.meta.env.VITE_TIANDITU_TOKEN ?? ''
const hasTiandituToken = computed(() => TIANDITU_TOKEN.trim().length > 0)
const TIANDITU_TILE =
  'https://t0.tianditu.gov.cn/{layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=' +
  TIANDITU_TOKEN
const DEFAULT_LOCATE_MAX_ZOOM = 16

const basemaps: Record<
  BasemapKey,
  {
    label: string
    layers: Array<{ id: string; sourceId: string; tileLayer: string }>
  }
> = {
  vector: {
    label: '矢量',
    layers: [
      { id: 'tdt-vec', sourceId: 'tiandituVec', tileLayer: 'vec' },
      { id: 'tdt-cva', sourceId: 'tiandituCva', tileLayer: 'cva' },
    ],
  },
  image: {
    label: '影像',
    layers: [
      { id: 'tdt-img', sourceId: 'tiandituImg', tileLayer: 'img' },
      { id: 'tdt-cia', sourceId: 'tiandituCia', tileLayer: 'cia' },
    ],
  },
  terrain: {
    label: '地形',
    layers: [
      { id: 'tdt-ter', sourceId: 'tiandituTer', tileLayer: 'ter' },
      { id: 'tdt-cta', sourceId: 'tiandituCta', tileLayer: 'cta' },
    ],
  },
}

const basemapOptions = Object.entries(basemaps).map(([key, item]) => ({
  key: key as BasemapKey,
  label: item.label,
}))
const allBasemapLayers = Object.values(basemaps).flatMap((item) =>
  item.layers.map((layer) => layer.id),
)

/** 把对象键或文件路径转换为浏览器可访问的工件地址。 */
function artifactUrl(objectKey?: string | null, filePath?: string | null) {
  const key = objectKey?.replaceAll('\\', '/').replace(/^\/+/, '')
  if (key) return `/artifacts/${key}`
  if (!filePath) return null
  const normalized = filePath.replaceAll('\\', '/')
  const marker = '/data/'
  const position = normalized.toLowerCase().lastIndexOf(marker)
  return position >= 0 ? `/artifacts/${normalized.slice(position + marker.length)}` : null
}

/** 构造后端动态 GeoTIFF 瓦片模板 URL。 */
function tileUrl(objectKey?: string | null) {
  const key = objectKey?.replaceAll('\\', '/').replace(/^\/+/, '')
  return key ? `/api/tiles/{z}/{x}/{y}.png?key=${encodeURIComponent(key)}` : null
}

/** 校验地理范围并转换为 MapLibre 边界对象。 */
function lngLatBounds(bounds?: [number, number, number, number] | null) {
  if (!bounds || bounds.length !== 4) return null
  const [west, south, east, north] = bounds
  const isLngLat =
    west >= -180 && east <= 180 && south >= -90 && north <= 90 && west < east && south < north
  return isLngLat ? bounds : null
}

const previewUrl = computed(() => {
  if (!props.product) return null
  return artifactUrl(props.product.previewObjectKey, props.product.previewPath)
})
const resultTileUrl = computed(() => tileUrl(props.product?.objectKey))

const assetPreviewUrl = computed(() => {
  if (!props.asset) return null
  return artifactUrl(props.asset.previewObjectKey, props.asset.previewPath)
})
const assetTileUrl = computed(() => tileUrl(props.asset?.objectKey))

const sourceBounds = computed<[number, number, number, number] | null>(() => {
  return lngLatBounds(props.asset?.metadata?.geographicBounds ?? props.asset?.metadata?.bounds)
})

const hasBeforePreview = computed(() =>
  Boolean((assetTileUrl.value || assetPreviewUrl.value) && sourceBounds.value),
)
const resultBounds = computed<[number, number, number, number] | null>(() => lngLatBounds(props.product?.bounds))
const statusText = computed(() => {
  if (props.product && (resultTileUrl.value || previewUrl.value)) return `${props.product.index.toUpperCase()} 结果`
  if (sourceBounds.value) return props.asset?.filename ?? '导入影像'
  if (props.asset) return '影像缺少经纬度范围'
  return '等待影像'
})
const sourceLayerLabel = computed(() => (assetTileUrl.value ? '导入影像 TIF' : hasBeforePreview.value ? '导入影像预览' : '影像范围'))
const sourceRenderMode = computed(() => {
  if (assetTileUrl.value && sourceTilesReady.value) return '原图 TIF 瓦片'
  if (assetTileUrl.value && assetPreviewUrl.value) return '预览就绪，原图瓦片加载中'
  if (assetTileUrl.value) return '原图 TIF，进入范围后加载'
  if (assetPreviewUrl.value) return 'PNG 预览'
  return '未加载'
})
const resultRenderMode = computed(() => {
  if (resultTileUrl.value && resultTilesInView.value) return '结果 TIF 瓦片'
  if (resultTileUrl.value) return '结果 TIF，进入范围后加载'
  if (previewUrl.value) return 'PNG 预览'
  return '未加载'
})
const resultLegend = computed(() => {
  const product = props.product
  if (!product) return null
  const statistics = product.statistics
  const minimum = statistics?.minimum ?? -1
  const maximum = statistics?.maximum ?? 1
  const center = statistics?.mean ?? (minimum + maximum) / 2
  return {
    title: product.index.toUpperCase(),
    name: product.name,
    minimum,
    center,
    maximum,
  }
})

/** 处理 formatLegendValue 对应的组件交互或数据转换逻辑。 */
function formatLegendValue(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'NA'
  return Math.abs(value) >= 10 ? value.toFixed(1) : value.toFixed(2)
}

/** 处理 setLayerVisibility 对应的组件交互或数据转换逻辑。 */
function setLayerVisibility(layerId: string, visible: boolean) {
  const instance = map.value
  if (!instance?.getLayer(layerId)) return
  instance.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
}

/** 处理 firstAnalysisLayerId 对应的组件交互或数据转换逻辑。 */
function firstAnalysisLayerId() {
  const instance = map.value
  if (!instance) return undefined
  return [
    'source-preview',
    'source-tiles',
    'vegetation-result-preview',
    'vegetation-result',
    'source-footprint-fill',
    'source-footprint-line',
  ].find((layerId) => instance.getLayer(layerId))
}

/** 按需创建天地图或兜底底图图层。 */
function ensureBasemapLayers(key: BasemapKey) {
  const instance = mapWhenStyleReady(() => ensureBasemapLayers(key))
  if (!instance) return
  const beforeId = firstAnalysisLayerId()
  for (const layer of basemaps[key].layers) {
    if (!instance.getSource(layer.sourceId)) {
      instance.addSource(layer.sourceId, {
        type: 'raster',
        tiles: [TIANDITU_TILE.replaceAll('{layer}', layer.tileLayer)],
        tileSize: 256,
        attribution: `天地图${basemaps[key].label}`,
      })
    }
    if (!instance.getLayer(layer.id)) {
      instance.addLayer(
        {
          id: layer.id,
          type: 'raster',
          source: layer.sourceId,
        },
        beforeId,
      )
    }
  }
}

/** 保证任一时刻只有当前底图可见。 */
function syncBasemapVisibility() {
  ensureBasemapLayers(activeBasemap.value)
  for (const layerId of allBasemapLayers) {
    const isActive = basemaps[activeBasemap.value].layers.some((layer) => layer.id === layerId)
    setLayerVisibility(layerId, layerState.basemap && isActive)
  }
}

/** 处理 shouldShowSourcePreview 对应的组件交互或数据转换逻辑。 */
function shouldShowSourcePreview() {
  return layerState.sourcePreview && compareMode.value !== 'after'
}

/** 处理 shouldShowFootprint 对应的组件交互或数据转换逻辑。 */
function shouldShowFootprint() {
  return layerState.footprint && compareMode.value !== 'after'
}

/** 处理 shouldShowResult 对应的组件交互或数据转换逻辑。 */
function shouldShowResult() {
  return layerState.result && compareMode.value !== 'before'
}

/** 在 MapLibre 样式完成后执行图层命令，避免时序异常。 */
function mapWhenStyleReady(callback: () => void) {
  const instance = map.value
  if (!instance) return null
  if (!mapReady) {
    instance.once('load', callback)
    return null
  }
  return instance
}

/** 固定范围、源影像和分析结果的图层叠放顺序。 */
function orderAnalysisLayers() {
  const instance = map.value
  if (!instance?.isStyleLoaded()) return
  if (instance.getLayer('source-tiles')) instance.moveLayer('source-tiles')
  if (instance.getLayer('vegetation-result-preview')) instance.moveLayer('vegetation-result-preview')
  if (instance.getLayer('vegetation-result')) instance.moveLayer('vegetation-result')
  if (instance.getLayer('source-footprint-line')) instance.moveLayer('source-footprint-line')
}

/** 安全移除指定图层及其数据源。 */
function removeLayerAndSource(layerId: string, sourceId = layerId) {
  const instance = map.value
  if (!instance) return
  if (instance.getLayer(layerId)) instance.removeLayer(layerId)
  if (instance.getSource(sourceId)) instance.removeSource(sourceId)
}

/** 判断两个经纬度包围盒是否相交。 */
function boundsIntersect(left: [number, number, number, number], right: [number, number, number, number]) {
  return left[0] <= right[2] && left[2] >= right[0] && left[1] <= right[3] && left[3] >= right[1]
}

/** 判断影像范围是否已位于当前地图视野。 */
function isBoundsInViewport(bounds: [number, number, number, number] | null) {
  const instance = map.value
  if (!instance || !bounds) return false
  const mapBounds = instance.getBounds()
  const visible: [number, number, number, number] = [
    mapBounds.getWest(),
    mapBounds.getSouth(),
    mapBounds.getEast(),
    mapBounds.getNorth(),
  ]
  return boundsIntersect(bounds, visible)
}

/** 触发 MapLibre 重新评估当前视口的瓦片请求。 */
function refreshTileDemand() {
  sourceTilesInView.value = Boolean(layerState.sourcePreview && isBoundsInViewport(sourceBounds.value))
  resultTilesInView.value = Boolean(layerState.result && isBoundsInViewport(resultBounds.value))
}

/** 源影像瓦片可用后切换占位预览，减少空白闪烁。 */
function promoteSourceTilesIfReady() {
  const instance = map.value
  if (
    sourceTilesReady.value
    || !instance?.getSource('source-tiles')
    || !isBoundsInViewport(sourceBounds.value)
    || !instance.isSourceLoaded('source-tiles')
  ) return
  sourceTilesReady.value = true
  syncSourcePaint()
}

/** 同步源影像透明度和对比模式裁剪参数。 */
function syncSourcePaint() {
  const instance = map.value
  if (!instance) return
  const showSource = shouldShowSourcePreview()
  const showPreview = showSource && Boolean(assetPreviewUrl.value) && !sourceTilesReady.value
  const showTiles =
    showSource && Boolean(assetTileUrl.value) && (sourceTilesReady.value || !assetPreviewUrl.value)
  if (instance.getLayer('source-preview')) {
    instance.setPaintProperty('source-preview', 'raster-opacity', showPreview ? 0.92 : 0)
  }
  if (instance.getLayer('source-tiles')) {
    instance.setPaintProperty('source-tiles', 'raster-opacity', showTiles ? 0.92 : 0)
  }
  if (instance.getLayer('source-footprint-fill')) {
    instance.setPaintProperty(
      'source-footprint-fill',
      'fill-opacity',
      shouldShowFootprint() && !assetPreviewUrl.value && !assetTileUrl.value ? 0.16 : 0,
    )
  }
  if (instance.getLayer('source-footprint-line')) {
    instance.setPaintProperty(
      'source-footprint-line',
      'line-opacity',
      shouldShowFootprint() ? 0.9 : 0,
    )
  }
}

/** 根据资产状态创建、更新或移除源影像图层。 */
function syncSourceLayer() {
  const instance = mapWhenStyleReady(syncSourceLayer)
  if (!instance) return
  const signature = JSON.stringify([
    assetTileUrl.value,
    assetPreviewUrl.value,
    sourceBounds.value,
  ])
  if (signature === renderedSourceSignature) {
    syncSourcePaint()
    return
  }
  renderedSourceSignature = signature
  sourceTilesReady.value = false
  removeLayerAndSource('source-tiles')
  removeLayerAndSource('source-preview')
  if (instance.getLayer('source-footprint-line')) instance.removeLayer('source-footprint-line')
  if (instance.getLayer('source-footprint-fill')) instance.removeLayer('source-footprint-fill')
  if (instance.getSource('source-footprint')) instance.removeSource('source-footprint')
  if (!sourceBounds.value) return
  const [west, south, east, north] = sourceBounds.value
  if (assetPreviewUrl.value) {
    const resultLayerId = instance.getLayer('vegetation-result') ? 'vegetation-result' : undefined
    instance.addSource('source-preview', {
      type: 'image',
      url: assetPreviewUrl.value,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    })
    instance.addLayer({
      id: 'source-preview',
      type: 'raster',
      source: 'source-preview',
      paint: {
        'raster-opacity': shouldShowSourcePreview() ? 0.92 : 0,
        'raster-fade-duration': 0,
      },
    }, resultLayerId)
  }
  if (assetTileUrl.value) {
    const resultLayerId = instance.getLayer('vegetation-result-preview')
      ? 'vegetation-result-preview'
      : instance.getLayer('vegetation-result')
        ? 'vegetation-result'
        : undefined
    instance.addSource('source-tiles', {
      type: 'raster',
      tiles: [assetTileUrl.value],
      tileSize: 256,
      bounds: [west, south, east, north],
    })
    instance.addLayer({
      id: 'source-tiles',
      type: 'raster',
      source: 'source-tiles',
      paint: {
        'raster-opacity': assetPreviewUrl.value ? 0 : shouldShowSourcePreview() ? 0.92 : 0,
        'raster-fade-duration': 0,
      },
    }, resultLayerId)
  }
  instance.addSource('source-footprint', {
    type: 'geojson',
    data: {
      type: 'Feature',
      properties: {},
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
          ],
        ],
      },
    },
  })
  const resultLayerId = instance.getLayer('vegetation-result') ? 'vegetation-result' : undefined
  instance.addLayer({
    id: 'source-footprint-fill',
    type: 'fill',
    source: 'source-footprint',
    paint: {
      'fill-color': '#58a6ff',
      'fill-opacity': shouldShowFootprint() && !assetPreviewUrl.value && !assetTileUrl.value ? 0.16 : 0,
    },
  }, resultLayerId)
  instance.addLayer({
    id: 'source-footprint-line',
    type: 'line',
    source: 'source-footprint',
    paint: {
      'line-color': '#58a6ff',
      'line-width': 2,
      'line-opacity': shouldShowFootprint() ? 0.9 : 0,
    },
  })
  syncSourcePaint()
  orderAnalysisLayers()
}

/** 根据当前产品创建、更新或移除指数结果图层。 */
function syncProductLayer() {
  const instance = mapWhenStyleReady(syncProductLayer)
  if (!instance) return
  const tileSourceUrl = resultTileUrl.value
  const imagePreviewUrl = resultTileUrl.value ? null : previewUrl.value
  const signature = JSON.stringify([tileSourceUrl, imagePreviewUrl, resultBounds.value])
  if (signature === renderedProductSignature) {
    if (instance.getLayer('vegetation-result')) {
      instance.setPaintProperty(
        'vegetation-result',
        'raster-opacity',
        shouldShowResult() ? opacity.value : 0,
      )
    }
    if (instance.getLayer('vegetation-result-preview')) {
      instance.setPaintProperty(
        'vegetation-result-preview',
        'raster-opacity',
        shouldShowResult() ? Math.max(opacity.value * 0.62, 0.22) : 0,
      )
    }
    return
  }
  renderedProductSignature = signature
  removeLayerAndSource('vegetation-result')
  removeLayerAndSource('vegetation-result-preview')
  if (!props.product || (!tileSourceUrl && !imagePreviewUrl) || !resultBounds.value) return
  const [west, south, east, north] = resultBounds.value
  if (imagePreviewUrl) {
    instance.addSource('vegetation-result-preview', {
      type: 'image',
      url: imagePreviewUrl,
      coordinates: [
        [west, north],
        [east, north],
        [east, south],
        [west, south],
      ],
    })
    instance.addLayer({
      id: 'vegetation-result-preview',
      type: 'raster',
      source: 'vegetation-result-preview',
      paint: {
        'raster-opacity': shouldShowResult() ? Math.max(opacity.value * 0.62, 0.22) : 0,
        'raster-fade-duration': 0,
      },
    })
  }
  if (tileSourceUrl) {
    instance.addSource('vegetation-result', {
      type: 'raster',
      tiles: [tileSourceUrl],
      tileSize: 256,
      bounds: [west, south, east, north],
    })
    instance.addLayer({
      id: 'vegetation-result',
      type: 'raster',
      source: 'vegetation-result',
      paint: {
        'raster-opacity': shouldShowResult() ? opacity.value : 0,
        'raster-fade-duration': 0,
      },
    })
  }
  orderAnalysisLayers()
}

/** 按影像覆盖范围估算合理最大定位级别。 */
function adaptiveMaxZoom(bounds: [number, number, number, number]) {
  const [west, south, east, north] = bounds
  const span = Math.max(Math.abs(east - west), Math.abs(north - south))
  if (span < 0.02) return DEFAULT_LOCATE_MAX_ZOOM
  if (span < 0.08) return 15
  if (span < 0.5) return 13
  if (span < 2) return 11
  return 9
}

/** 以防抖和原因标记控制地图定位，避免重复飞行动画。 */
function fitBounds(bounds: [number, number, number, number] | null, reason: 'auto' | 'manual' = 'manual') {
  const instance = map.value
  if (!instance) return
  if (!mapReady) {
    instance.once('load', () => fitBounds(bounds, reason))
    return
  }
  if (!bounds) return
  const [west, south, east, north] = bounds
  const targetBounds: [[number, number], [number, number]] = [
    [west, south],
    [east, north],
  ]
  const maxZoom = adaptiveMaxZoom(bounds)
  const options = { padding: 72, duration: 650, maxZoom }
  const center: [number, number] = [(west + east) / 2, (south + north) / 2]
  const isSmallFootprint = Math.max(Math.abs(east - west), Math.abs(north - south)) < 0.05
  if (isSmallFootprint) {
    instance.easeTo({ center, zoom: maxZoom, duration: options.duration })
  } else {
    instance.fitBounds(targetBounds, options)
  }
  window.setTimeout(() => {
    refreshTileDemand()
    syncMapLayers()
  }, options.duration + 80)
  if (reason === 'auto') pendingSourceLocateKey = ''
}

/** 响应用户定位按钮并强制定位到目标范围。 */
function locateManually(bounds: [number, number, number, number] | null) {
  fitBounds(bounds, 'manual')
}

/** 在样式可用时统一同步底图、源影像和结果图层。 */
function syncMapLayers() {
  refreshTileDemand()
  syncBasemapVisibility()
  syncSourceLayer()
  syncProductLayer()
}

/** 只在必要时自动定位新导入影像。 */
function autoLocate(bounds: [number, number, number, number] | null) {
  if (!bounds) return
  fitBounds(bounds, 'auto')
}

/** 完成异步图层准备后执行待处理定位。 */
function locateImportedAssetIfPending() {
  if (!pendingSourceLocateKey) return
  autoLocate(sourceBounds.value)
}

/** 隐藏分析图层，仅保留底图。 */
function showOnlyBasemap() {
  layerState.basemap = true
  layerState.sourcePreview = false
  layerState.footprint = false
  layerState.result = false
}

/** 恢复源影像、范围和结果图层。 */
function showAnalysisLayers() {
  layerState.sourcePreview = true
  layerState.footprint = true
  layerState.result = true
  syncMapLayers()
}

/** 切换正常、并排或卷帘对比状态。 */
function setCompareMode(mode: CompareMode) {
  compareMode.value = mode
  syncMapLayers()
}

watch(
  () => props.asset?.objectKey ?? props.asset?.localPath ?? '',
  (key) => {
    syncMapLayers()
    if (!key || seenSourceKeys.has(key)) return
    seenSourceKeys.add(key)
    pendingSourceLocateKey = key
    locateImportedAssetIfPending()
  },
  { immediate: true },
)
watch(
  () => props.product?.objectKey ?? props.product?.path ?? '',
  () => {
    syncMapLayers()
  },
)
watch(sourceBounds, () => {
  syncMapLayers()
  locateImportedAssetIfPending()
})
watch(activeBasemap, syncBasemapVisibility)
watch(layerState, () => {
  syncMapLayers()
})
watch(compareMode, () => {
  syncMapLayers()
})
watch(opacity, (value) => {
  if (map.value?.getLayer('vegetation-result')) {
    map.value.setPaintProperty(
      'vegetation-result',
      'raster-opacity',
      shouldShowResult() ? value : 0,
    )
  }
  if (map.value?.getLayer('vegetation-result-preview')) {
    map.value.setPaintProperty(
      'vegetation-result-preview',
      'raster-opacity',
      shouldShowResult() ? Math.max(value * 0.62, 0.22) : 0,
    )
  }
})

onMounted(() => {
  if (!mapContainer.value) return
  const instance = new maplibregl.Map({
    container: mapContainer.value,
    center: [105, 35],
    zoom: 3.2,
    attributionControl: false,
    style: {
      version: 8,
      sources: {},
      layers: [],
    },
  })
  instance.addControl(new maplibregl.NavigationControl(), 'top-right')
  instance.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
  instance.addControl(new maplibregl.ScaleControl({ maxWidth: 140, unit: 'metric' }), 'bottom-right')
  instance.on('mousemove', (event) => {
    cursorCoordinates.value = `${event.lngLat.lng.toFixed(5)}, ${event.lngLat.lat.toFixed(5)}`
  })
  instance.on('rotate', () => {
    mapBearing.value = instance.getBearing()
  })
  instance.on('moveend', () => {
    mapBearing.value = instance.getBearing()
    refreshTileDemand()
    promoteSourceTilesIfReady()
  })
  instance.on('sourcedata', (event) => {
    if (event.sourceId === 'source-tiles') promoteSourceTilesIfReady()
  })
  instance.on('load', () => {
    mapReady = true
    syncMapLayers()
    locateImportedAssetIfPending()
  })
  map.value = instance
  if (import.meta.env.DEV) {
    ;(window as Window & { __vipMap?: Map }).__vipMap = instance
  }
  resizeObserver = new ResizeObserver(() => instance.resize())
  resizeObserver.observe(mapContainer.value)
})

onBeforeUnmount(() => {
  mapReady = false
  resizeObserver?.disconnect()
  map.value?.remove()
})
</script>

<template>
  <section class="map-shell">
    <div ref="mapContainer" class="map-canvas" />
    <div class="map-topline">
      <span class="live-dot" />
      <span>遥感地图工作区</span>
      <strong>{{ statusText }}</strong>
    </div>
    <div class="coordinate-chip">
      <span>CURSOR</span>
      {{ cursorCoordinates }}
    </div>
    <div class="north-arrow" aria-label="指北针">
      <div class="north-pointer" :style="{ transform: `rotate(${-mapBearing}deg)` }">N</div>
      <span>北</span>
    </div>
    <div v-if="resultLegend" class="result-legend" aria-label="结果颜色条">
      <div class="legend-head">
        <strong>{{ resultLegend.title }}</strong>
        <span>{{ resultLegend.name }}</span>
      </div>
      <div class="legend-ramp" />
      <div class="legend-values">
        <span>{{ formatLegendValue(resultLegend.minimum) }}</span>
        <span>{{ formatLegendValue(resultLegend.center) }}</span>
        <span>{{ formatLegendValue(resultLegend.maximum) }}</span>
      </div>
    </div>
    <div v-if="!hasTiandituToken" class="token-warning">
      <strong>天地图 Token 未配置</strong>
      <span>在本地 `.env` 设置 VITE_TIANDITU_TOKEN 后会显示在线底图</span>
    </div>
    <aside class="layer-control" aria-label="图层控制">
      <header class="layer-panel-header">
        <span>LAYERS</span>
        <button type="button" @click="showOnlyBasemap">只看底图</button>
      </header>
      <div class="layer-row">
        <label>
          <input v-model="layerState.basemap" type="checkbox" />
          <strong>天地图底图</strong>
        </label>
        <div class="segmented-control">
          <button
            v-for="item in basemapOptions"
            :key="item.key"
            type="button"
            :class="{ active: activeBasemap === item.key }"
            :disabled="!layerState.basemap"
            @click="activeBasemap = item.key"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <div class="layer-row">
        <label>
          <input v-model="layerState.sourcePreview" type="checkbox" :disabled="!sourceBounds" />
          <strong>{{ sourceLayerLabel }}</strong>
        </label>
        <button type="button" class="zoom-button" :disabled="!sourceBounds" @click="locateManually(sourceBounds)">
          定位
        </button>
      </div>
      <div class="layer-row">
        <label>
          <input v-model="layerState.result" type="checkbox" :disabled="!product" />
          <strong>计算结果</strong>
        </label>
        <button type="button" class="zoom-button" :disabled="!resultBounds" @click="locateManually(resultBounds)">
          定位
        </button>
      </div>
      <div v-if="(products?.length ?? 0) > 1" class="control-group">
        <span>结果指数</span>
        <div class="product-switcher">
          <button
            v-for="(item, index) in products"
            :key="`${item.index}-${item.path}`"
            type="button"
            :class="{ active: index === activeProductIndex }"
            @click="emit('selectProduct', index)"
          >
            {{ item.index.toUpperCase() }}
          </button>
        </div>
      </div>
      <div class="layer-row">
        <label>
          <input v-model="layerState.footprint" type="checkbox" :disabled="!sourceBounds" />
          <strong>范围框</strong>
        </label>
        <button type="button" class="zoom-button" :disabled="!sourceBounds" @click="locateManually(sourceBounds)">
          定位
        </button>
      </div>
      <div class="control-group">
        <span>显示模式</span>
        <div class="segmented-control">
          <button
            type="button"
            :class="{ active: compareMode === 'before' }"
            :disabled="!sourceBounds"
            @click="setCompareMode('before')"
          >
            计算前
          </button>
          <button
            type="button"
            :class="{ active: compareMode === 'after' }"
            :disabled="!product"
            @click="setCompareMode('after')"
          >
            计算后
          </button>
          <button
            type="button"
            :class="{ active: compareMode === 'both' }"
            :disabled="!sourceBounds && !product"
            @click="setCompareMode('both')"
          >
            对比
          </button>
        </div>
      </div>
      <label class="opacity-control" for="opacity">
        <span>结果透明度 {{ Math.round(opacity * 100) }}%</span>
        <input id="opacity" v-model.number="opacity" type="range" min="0" max="1" step="0.01" />
      </label>
      <div class="layer-status">
        <p>
          <span>源图层</span>
          <strong>{{ sourceRenderMode }}</strong>
        </p>
        <p>
          <span>结果图层</span>
          <strong>{{ resultRenderMode }}</strong>
        </p>
      </div>
      <button type="button" class="restore-button" @click="showAnalysisLayers">恢复分析图层</button>
    </aside>
    <div v-if="asset && !sourceBounds && !product" class="empty-state">
      <div class="scan-mark" />
      <p>影像缺少地理坐标</p>
      <span>当前影像无法和天地图对齐，请选择有 CRS 和 bounds 的 GeoTIFF</span>
    </div>
  </section>
</template>

<style scoped>
.map-shell {
  position: relative;
  min-width: 0;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
}

.map-canvas {
  position: absolute;
  inset: 0;
}

.map-shell :deep(.maplibregl-ctrl-top-right) {
  top: 74px;
  right: 18px;
}

.map-shell :deep(.maplibregl-ctrl-bottom-left) {
  bottom: 56px;
  left: 18px;
}

.map-shell :deep(.maplibregl-ctrl-bottom-right) {
  right: 18px;
  bottom: 22px;
}

.map-shell :deep(.maplibregl-ctrl-group),
.map-shell :deep(.maplibregl-ctrl-attrib),
.map-shell :deep(.maplibregl-ctrl-scale) {
  border: 1px solid var(--border-strong);
  background: color-mix(in srgb, var(--surface-1) 88%, transparent);
  box-shadow: none;
  backdrop-filter: blur(16px);
}

.map-shell :deep(.maplibregl-ctrl button) {
  width: 34px;
  height: 34px;
}

.map-shell :deep(.maplibregl-ctrl-scale) {
  min-width: 128px;
  padding: 7px 12px 8px;
  border-top: 0;
  border-right: 0;
  border-left: 0;
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
}

.map-topline,
.coordinate-chip,
.north-arrow,
.result-legend,
.layer-control,
.token-warning {
  position: absolute;
  z-index: 2;
  background: color-mix(in srgb, var(--surface-1) 88%, transparent);
  border: 1px solid var(--border-strong);
  backdrop-filter: blur(16px);
}

.map-topline {
  top: 18px;
  left: 18px;
  right: 18px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 15px;
  font-family: var(--font-mono);
  font-size: 13px;
}

.map-topline strong {
  margin-left: auto;
  color: var(--acid);
  font-weight: 600;
}

.live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 15px var(--accent);
  animation: pulse 1.8s infinite;
}

.coordinate-chip {
  left: 18px;
  bottom: 18px;
  padding: 10px 13px;
  color: var(--text-1);
  font-family: var(--font-mono);
  font-size: 12px;
}

.coordinate-chip span {
  margin-right: 8px;
  color: var(--muted);
}

.north-arrow {
  top: 196px;
  right: 18px;
  display: grid;
  width: 48px;
  height: 58px;
  place-items: center;
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 10px;
  box-shadow: 0 10px 28px rgb(0 0 0 / 12%);
}

.north-pointer {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  clip-path: polygon(50% 0, 82% 100%, 50% 78%, 18% 100%);
  background: var(--acid);
  color: var(--surface-0);
  font-weight: 900;
  transform-origin: 50% 50%;
}

.north-arrow span {
  margin-top: -4px;
}

.result-legend {
  right: 18px;
  bottom: 72px;
  display: grid;
  width: min(260px, calc(100% - 360px));
  gap: 8px;
  padding: 10px 12px;
}

.legend-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.legend-head strong {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
}

.legend-head span {
  overflow: hidden;
  color: var(--text-2);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.legend-ramp {
  height: 12px;
  border: 1px solid var(--border-strong);
  background: linear-gradient(90deg, #26546c 0%, #6d8f55 46%, #b2f22a 100%);
}

.legend-values {
  display: flex;
  justify-content: space-between;
  color: var(--text-2);
  font-family: var(--font-mono);
  font-size: 11px;
}

.token-warning {
  left: 18px;
  bottom: 72px;
  display: grid;
  max-width: min(360px, calc(100% - 396px));
  gap: 5px;
  padding: 10px 12px;
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.45;
}

.token-warning strong {
  color: var(--acid);
  font-size: 13px;
}

.layer-control {
  top: 76px;
  left: 18px;
  display: grid;
  width: min(310px, calc(100% - 36px));
  gap: 10px;
  padding: 14px;
}

.layer-panel-header,
.layer-row,
.control-group,
.opacity-control {
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}

.layer-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 800;
}

.layer-panel-header button,
.zoom-button,
.restore-button {
  border: 1px solid var(--border-strong);
  background: var(--surface-2);
  color: var(--text-1);
  font-size: 12px;
  cursor: pointer;
}

.layer-panel-header button {
  padding: 5px 8px;
}

.layer-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.layer-row label {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 8px;
  color: var(--text-1);
  font-size: 13px;
}

.layer-row input {
  accent-color: var(--acid);
}

.layer-row strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.zoom-button {
  padding: 5px 8px;
}

.restore-button {
  min-height: 34px;
  color: var(--acid);
  font-family: var(--font-mono);
  font-weight: 800;
}

.zoom-button:disabled,
.restore-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.control-group > span,
.opacity-control span {
  display: block;
  margin-bottom: 8px;
  color: var(--text-1);
  font-size: 13px;
  font-weight: 600;
}

.segmented-control {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.segmented-control button,
.product-switcher button {
  min-height: 34px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
}

.segmented-control button.active,
.product-switcher button.active {
  border-color: var(--accent-strong);
  background: var(--surface-hover);
  color: var(--accent-strong);
}

.segmented-control button:disabled,
.product-switcher button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.product-switcher {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.product-switcher button {
  min-height: 30px;
  padding: 5px 8px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.opacity-control input {
  width: 100%;
  accent-color: var(--acid);
}

.layer-status {
  display: grid;
  gap: 6px;
  padding-top: 2px;
}

.layer-status p {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin: 0;
  color: var(--text-2);
  font-size: 12px;
}

.layer-status strong {
  color: var(--text-1);
}

.empty-state {
  position: absolute;
  z-index: 1;
  top: 50%;
  left: 50%;
  text-align: center;
  transform: translate(-50%, -50%);
  color: var(--text-1);
}

.empty-state p {
  margin: 18px 0 6px;
  font-family: var(--font-display);
  font-size: 26px;
}

.empty-state span {
  color: var(--muted);
  font-size: 14px;
}

.scan-mark {
  width: 54px;
  height: 54px;
  margin: auto;
  border: 1px solid var(--accent);
  transform: rotate(45deg);
  box-shadow:
    inset 0 0 24px color-mix(in srgb, var(--accent) 14%, transparent),
    0 0 28px color-mix(in srgb, var(--accent) 12%, transparent);
}

@media (max-width: 1100px) {
  .map-shell {
    height: clamp(420px, 62dvh, 720px);
    min-height: 420px;
  }

  .map-topline {
    right: 12px;
    left: 12px;
  }

  .map-topline > span:nth-child(2) {
    display: none;
  }

  .coordinate-chip {
    right: 12px;
    bottom: 260px;
    left: 12px;
  }

  .north-arrow {
    top: 114px;
    right: 12px;
  }

  .result-legend {
    right: 12px;
    bottom: 386px;
    left: 12px;
    width: auto;
  }

  .token-warning {
    right: 12px;
    bottom: 308px;
    left: 12px;
    max-width: none;
  }

  .layer-control {
    top: auto;
    right: 12px;
    bottom: 54px;
    left: 12px;
    width: auto;
    max-height: 320px;
    overflow: auto;
    gap: 7px;
    padding: 10px 12px;
  }

  .control-group > span,
  .opacity-control span {
    margin-bottom: 6px;
    font-size: 12px;
  }

  .segmented-control button {
    min-height: 30px;
    font-size: 12px;
  }

  .layer-status {
    display: none;
  }

  .map-shell :deep(.maplibregl-ctrl-top-right) {
    top: 68px;
    right: 12px;
  }

  .map-shell :deep(.maplibregl-ctrl-bottom-left) {
    bottom: 252px;
    left: 12px;
  }

  .map-shell :deep(.maplibregl-ctrl-bottom-right) {
    right: 12px;
    bottom: 12px;
  }
}

@keyframes pulse {
  50% {
    opacity: 0.25;
  }
}
</style>
