<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue'
import maplibregl, { type Map } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { Product, UploadedAsset } from '@/types/platform'

const props = defineProps<{
  asset: UploadedAsset | null
  product: Product | null
}>()

type BasemapKey = 'vector' | 'image' | 'terrain'
type CompareMode = 'before' | 'after' | 'both'

const mapContainer = useTemplateRef<HTMLDivElement>('mapContainer')
const map = shallowRef<Map | null>(null)
let resizeObserver: ResizeObserver | undefined
const opacity = defineModel<number>('opacity', { default: 0.78 })
const cursorCoordinates = shallowRef('将鼠标移入地图读取坐标')
const activeBasemap = shallowRef<BasemapKey>('image')
const compareMode = shallowRef<CompareMode>('both')
const TIANDITU_TOKEN = import.meta.env.VITE_TIANDITU_TOKEN ?? ''
const hasTiandituToken = computed(() => TIANDITU_TOKEN.trim().length > 0)
const TIANDITU_TILE =
  'https://t0.tianditu.gov.cn/{layer}_w/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={layer}&STYLE=default&TILEMATRIXSET=w&FORMAT=tiles&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}&tk=' +
  TIANDITU_TOKEN

const basemaps: Record<BasemapKey, { label: string; layers: string[] }> = {
  vector: { label: '矢量', layers: ['tdt-vec', 'tdt-cva'] },
  image: { label: '影像', layers: ['tdt-img', 'tdt-cia'] },
  terrain: { label: '地形', layers: ['tdt-ter', 'tdt-cta'] },
}

const basemapOptions = Object.entries(basemaps).map(([key, item]) => ({
  key: key as BasemapKey,
  label: item.label,
}))
const allBasemapLayers = Object.values(basemaps).flatMap((item) => item.layers)

const previewUrl = computed(() => {
  if (!props.product?.previewPath) return null
  const normalized = props.product.previewPath.replaceAll('\\', '/')
  const marker = '/data/'
  const position = normalized.toLowerCase().lastIndexOf(marker)
  return position >= 0 ? `/artifacts/${normalized.slice(position + marker.length)}` : null
})

const assetPreviewUrl = computed(() => {
  if (!props.asset?.previewPath) return null
  const normalized = props.asset.previewPath.replaceAll('\\', '/')
  const marker = '/data/'
  const position = normalized.toLowerCase().lastIndexOf(marker)
  return position >= 0 ? `/artifacts/${normalized.slice(position + marker.length)}` : null
})

const sourceBounds = computed<[number, number, number, number] | null>(() => {
  const bounds = props.asset?.metadata?.geographicBounds ?? props.asset?.metadata?.bounds
  if (!bounds || bounds.length !== 4) return null
  const [west, south, east, north] = bounds
  const isLngLat =
    west >= -180 && east <= 180 && south >= -90 && north <= 90 && west < east && south < north
  return isLngLat ? [west, south, east, north] : null
})

const shouldShowBasemap = computed(() => true)
const hasBeforePreview = computed(() => Boolean(assetPreviewUrl.value && sourceBounds.value))
const statusText = computed(() => {
  if (props.product && previewUrl.value) return `正在查看 ${props.product.index.toUpperCase()} 结果`
  if (sourceBounds.value) return '已读取导入影像空间范围，等待计算结果'
  if (props.asset) return '影像缺少可用经纬度范围，已关闭底图叠加'
  return '导入影像后显示空间范围和计算结果'
})

function setLayerVisibility(layerId: string, visible: boolean) {
  const instance = map.value
  if (!instance?.getLayer(layerId)) return
  instance.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
}

function syncBasemapVisibility() {
  for (const layerId of allBasemapLayers) {
    const isActive = basemaps[activeBasemap.value].layers.includes(layerId)
    setLayerVisibility(layerId, shouldShowBasemap.value && isActive)
  }
}

function syncSourceLayer() {
  const instance = map.value
  if (!instance?.isStyleLoaded()) return
  if (instance.getLayer('source-preview')) instance.removeLayer('source-preview')
  if (instance.getSource('source-preview')) instance.removeSource('source-preview')
  if (instance.getLayer('source-footprint-line')) instance.removeLayer('source-footprint-line')
  if (instance.getLayer('source-footprint-fill')) instance.removeLayer('source-footprint-fill')
  if (instance.getSource('source-footprint')) instance.removeSource('source-footprint')
  if (!sourceBounds.value) return
  const [west, south, east, north] = sourceBounds.value
  if (assetPreviewUrl.value) {
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
        'raster-opacity': compareMode.value === 'after' ? 0 : 0.92,
        'raster-fade-duration': 0,
      },
    })
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
  instance.addLayer({
    id: 'source-footprint-fill',
    type: 'fill',
    source: 'source-footprint',
    paint: {
      'fill-color': '#58a6ff',
      'fill-opacity': compareMode.value === 'after' || assetPreviewUrl.value ? 0 : 0.16,
    },
  })
  instance.addLayer({
    id: 'source-footprint-line',
    type: 'line',
    source: 'source-footprint',
    paint: {
      'line-color': '#58a6ff',
      'line-width': 2,
      'line-opacity': compareMode.value === 'after' ? 0 : 0.9,
    },
  })
}

function syncProductLayer() {
  const instance = map.value
  if (!instance?.isStyleLoaded()) return
  if (instance.getLayer('vegetation-result')) instance.removeLayer('vegetation-result')
  if (instance.getSource('vegetation-result')) instance.removeSource('vegetation-result')
  if (!props.product || !previewUrl.value) return
  const [west, south, east, north] = props.product.bounds
  instance.addSource('vegetation-result', {
    type: 'image',
    url: previewUrl.value,
    coordinates: [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ],
  })
  instance.addLayer({
    id: 'vegetation-result',
    type: 'raster',
    source: 'vegetation-result',
    paint: {
      'raster-opacity': compareMode.value === 'before' ? 0 : opacity.value,
      'raster-fade-duration': 0,
    },
  })
}

function fitActiveBounds() {
  const instance = map.value
  if (!instance?.isStyleLoaded()) return
  const bounds = props.product?.bounds ?? sourceBounds.value
  if (!bounds) return
  const [west, south, east, north] = bounds
  instance.fitBounds(
    [
      [west, south],
      [east, north],
    ],
    { padding: 72, duration: 900 },
  )
}

function syncMapLayers() {
  syncBasemapVisibility()
  syncSourceLayer()
  syncProductLayer()
  fitActiveBounds()
}

watch(() => props.product, syncMapLayers)
watch(() => props.asset, syncMapLayers)
watch(sourceBounds, syncMapLayers)
watch(activeBasemap, syncBasemapVisibility)
watch(compareMode, () => {
  if (map.value?.getLayer('source-footprint-fill')) {
    map.value.setPaintProperty(
      'source-footprint-fill',
      'fill-opacity',
      compareMode.value === 'after' || assetPreviewUrl.value ? 0 : 0.16,
    )
  }
  if (map.value?.getLayer('source-footprint-line')) {
    map.value.setPaintProperty(
      'source-footprint-line',
      'line-opacity',
      compareMode.value === 'after' ? 0 : 0.9,
    )
  }
  if (map.value?.getLayer('vegetation-result')) {
    map.value.setPaintProperty(
      'vegetation-result',
      'raster-opacity',
      compareMode.value === 'before' ? 0 : opacity.value,
    )
  }
  if (map.value?.getLayer('source-preview')) {
    map.value.setPaintProperty(
      'source-preview',
      'raster-opacity',
      compareMode.value === 'after' ? 0 : 0.92,
    )
  }
})
watch(opacity, (value) => {
  if (map.value?.getLayer('vegetation-result')) {
    map.value.setPaintProperty(
      'vegetation-result',
      'raster-opacity',
      compareMode.value === 'before' ? 0 : value,
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
      sources: {
        tiandituVec: {
          type: 'raster',
          tiles: [TIANDITU_TILE.replaceAll('{layer}', 'vec')],
          tileSize: 256,
          attribution: '天地图矢量',
        },
        tiandituCva: {
          type: 'raster',
          tiles: [TIANDITU_TILE.replaceAll('{layer}', 'cva')],
          tileSize: 256,
          attribution: '天地图注记',
        },
        tiandituImg: {
          type: 'raster',
          tiles: [TIANDITU_TILE.replaceAll('{layer}', 'img')],
          tileSize: 256,
          attribution: '天地图影像',
        },
        tiandituCia: {
          type: 'raster',
          tiles: [TIANDITU_TILE.replaceAll('{layer}', 'cia')],
          tileSize: 256,
          attribution: '天地图影像注记',
        },
        tiandituTer: {
          type: 'raster',
          tiles: [TIANDITU_TILE.replaceAll('{layer}', 'ter')],
          tileSize: 256,
          attribution: '天地图地形',
        },
        tiandituCta: {
          type: 'raster',
          tiles: [TIANDITU_TILE.replaceAll('{layer}', 'cta')],
          tileSize: 256,
          attribution: '天地图地形注记',
        },
      },
      layers: [
        { id: 'tdt-vec', type: 'raster', source: 'tiandituVec' },
        { id: 'tdt-cva', type: 'raster', source: 'tiandituCva' },
        { id: 'tdt-img', type: 'raster', source: 'tiandituImg' },
        { id: 'tdt-cia', type: 'raster', source: 'tiandituCia' },
        { id: 'tdt-ter', type: 'raster', source: 'tiandituTer' },
        { id: 'tdt-cta', type: 'raster', source: 'tiandituCta' },
      ],
    },
  })
  instance.addControl(new maplibregl.NavigationControl(), 'top-right')
  instance.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-left')
  instance.on('mousemove', (event) => {
    cursorCoordinates.value = `${event.lngLat.lng.toFixed(5)}, ${event.lngLat.lat.toFixed(5)}`
  })
  instance.on('load', syncMapLayers)
  map.value = instance
  resizeObserver = new ResizeObserver(() => instance.resize())
  resizeObserver.observe(mapContainer.value)
})

onBeforeUnmount(() => {
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
    <div v-if="!hasTiandituToken" class="token-warning">
      <strong>天地图 Token 未配置</strong>
      <span>在本地 `.env` 设置 VITE_TIANDITU_TOKEN 后会显示在线底图</span>
    </div>
    <div class="layer-control" aria-label="图层控制">
      <div class="control-group">
        <span>天地图底图</span>
        <div class="segmented-control">
          <button
            v-for="item in basemapOptions"
            :key="item.key"
            type="button"
            :class="{ active: activeBasemap === item.key }"
            :disabled="!shouldShowBasemap"
            @click="activeBasemap = item.key"
          >
            {{ item.label }}
          </button>
        </div>
      </div>
      <div class="control-group">
        <span>显示模式</span>
        <div class="segmented-control">
          <button
            type="button"
            :class="{ active: compareMode === 'before' }"
            :disabled="!sourceBounds"
            @click="compareMode = 'before'"
          >
            计算前
          </button>
          <button
            type="button"
            :class="{ active: compareMode === 'after' }"
            :disabled="!product"
            @click="compareMode = 'after'"
          >
            计算后
          </button>
          <button
            type="button"
            :class="{ active: compareMode === 'both' }"
            :disabled="!sourceBounds && !product"
            @click="compareMode = 'both'"
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
          <strong>导入影像</strong>
          {{
            hasBeforePreview
              ? '已加载预览'
              : sourceBounds
                ? '已定位'
                : asset
                  ? '缺少可叠加坐标'
                  : '未导入'
          }}
        </p>
        <p>
          <strong>计算结果</strong>
          {{ previewUrl ? '已加载预览' : product ? '缺少预览' : '未选择' }}
        </p>
      </div>
    </div>
    <div v-if="asset && !sourceBounds && !product" class="empty-state">
      <div class="scan-mark" />
      <p>影像缺少地理坐标</p>
      <span>当前影像无法和天地图对齐，请选择有 CRS 和 bounds 的 GeoTIFF</span>
    </div>
    <div v-else-if="sourceBounds && !hasBeforePreview" class="source-note">
      已显示导入影像范围。上传影像像素预览需要后端生成 PNG 或瓦片。
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

.map-shell :deep(.maplibregl-ctrl-group),
.map-shell :deep(.maplibregl-ctrl-attrib) {
  border: 1px solid var(--border-strong);
  background: color-mix(in srgb, var(--surface-1) 88%, transparent);
  box-shadow: none;
  backdrop-filter: blur(16px);
}

.map-shell :deep(.maplibregl-ctrl button) {
  width: 34px;
  height: 34px;
}

.map-topline,
.coordinate-chip,
.layer-control,
.token-warning,
.source-note {
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
  right: 18px;
  bottom: 18px;
  display: grid;
  width: min(360px, calc(100% - 36px));
  gap: 12px;
  padding: 14px;
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

.segmented-control button {
  min-height: 34px;
  border: 1px solid var(--border);
  background: var(--surface-2);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
}

.segmented-control button.active {
  border-color: var(--accent-strong);
  background: var(--surface-hover);
  color: var(--accent-strong);
}

.segmented-control button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
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

.source-note {
  right: 18px;
  bottom: 318px;
  max-width: 360px;
  padding: 10px 12px;
  color: var(--text-2);
  font-size: 12px;
  line-height: 1.5;
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

  .token-warning {
    right: 12px;
    bottom: 308px;
    left: 12px;
    max-width: none;
  }

  .layer-control {
    right: 12px;
    bottom: 54px;
    left: 12px;
    width: auto;
    gap: 7px;
    padding: 10px 12px;
  }

  .source-note {
    right: 12px;
    bottom: 258px;
    left: 12px;
    max-width: none;
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
}

@keyframes pulse {
  50% {
    opacity: 0.25;
  }
}
</style>
