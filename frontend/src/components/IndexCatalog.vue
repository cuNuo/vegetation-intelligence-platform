<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import type { IndexMetadata } from '@/types/platform'

const props = defineProps<{
  indices: IndexMetadata[]
}>()

const query = shallowRef('')
const activeCategory = shallowRef('all')
type FormulaTokenType = 'band' | 'function' | 'operator' | 'number' | 'parameter' | 'text'
interface FormulaToken {
  value: string
  type: FormulaTokenType
}

const bandTokens = new Set(['NIR', 'Red', 'Green', 'Blue', 'RedEdge', 'RE', 'SWIR1', 'SWIR2', 'NDVI'])
const functionTokens = new Set(['sqrt', 'max', 'sign', 'abs'])
const operatorTokens = new Set(['+', '-', '*', '/', '^', '(', ')', ','])

const categories = computed(() => [
  'all',
  ...new Set(props.indices.flatMap((item) => item.categories)),
])
const visibleIndices = computed(() => {
  const keyword = query.value.trim().toLowerCase()
  return props.indices.filter((item) => {
    const categoryMatches =
      activeCategory.value === 'all' || item.categories.includes(activeCategory.value)
    const keywordMatches =
      !keyword ||
      `${item.id} ${item.name} ${item.description} ${item.formula}`.toLowerCase().includes(keyword)
    return categoryMatches && keywordMatches
  })
})

function categoryLabel(category: string) {
  return category === 'all' ? '全部指数' : category
}

function rangeLabel(range: [number, number] | null) {
  if (!range) return '未限定'
  return `${range[0]} 至 ${range[1]}`
}

function tokenizeFormula(formula: string): FormulaToken[] {
  return Array.from(
    formula.matchAll(/RedEdge|SWIR[12]|NIR|Red|Green|Blue|NDVI|sqrt|max|sign|abs|[A-Z][A-Za-z0-9]*|\d+(?:\.\d+)?|[()+\-*/^,]/g),
  ).map(([value]) => {
    if (bandTokens.has(value)) return { value, type: 'band' }
    if (functionTokens.has(value)) return { value, type: 'function' }
    if (operatorTokens.has(value)) return { value, type: 'operator' }
    if (/^\d/.test(value)) return { value, type: 'number' }
    if (/^[A-Z]/.test(value)) return { value, type: 'parameter' }
    return { value, type: 'text' }
  })
}
</script>

<template>
  <section class="catalog">
    <header>
      <div>
        <span>INDEX REGISTRY / {{ indices.length || 35 }}</span>
        <h2>植被指数库</h2>
      </div>
      <input v-model="query" type="search" placeholder="搜索指数、用途或公式" />
    </header>
    <nav>
      <button
        v-for="category in categories"
        :key="category"
        :class="{ active: activeCategory === category }"
        @click="activeCategory = category"
      >
        {{ categoryLabel(category) }}
      </button>
    </nav>
    <div class="index-grid">
      <article v-for="item in visibleIndices" :key="item.id">
        <header class="card-header">
          <span class="card-index">{{ item.id.toUpperCase() }}</span>
          <strong>{{ item.name }}</strong>
        </header>
        <p>{{ item.description }}</p>
        <div class="formula-card" aria-label="植被指数公式">
          <span class="formula-label">FORMULA</span>
          <div class="formula-line">
            <span
              v-for="(token, tokenIndex) in tokenizeFormula(item.formula)"
              :key="`${item.id}-${tokenIndex}-${token.value}`"
              class="formula-token"
              :class="`token-${token.type}`"
            >
              {{ token.value }}
            </span>
          </div>
        </div>
        <dl>
          <div>
            <dt>范围</dt>
            <dd>{{ rangeLabel(item.expectedRange) }}</dd>
          </div>
          <div>
            <dt>波段</dt>
            <dd>
              <span v-for="band in item.requiredBands" :key="band">{{ band }}</span>
            </dd>
          </div>
        </dl>
        <small v-if="item.limitations.length">{{ item.limitations[0] }}</small>
      </article>
    </div>
  </section>
</template>

<style scoped>
.catalog {
  min-width: 0;
  padding: 28px;
  border: 1px solid var(--border-strong);
  background: var(--surface-1);
}

.catalog > header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
}

.catalog > header span {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
}

.catalog h2 {
  margin: 7px 0 0;
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 500;
}

.catalog input {
  width: min(340px, 42vw);
  padding: 11px 14px;
  border: 1px solid var(--border-strong);
  outline: 0;
  background: var(--surface-0);
  color: var(--text-1);
  font-size: 14px;
}

.catalog nav {
  display: flex;
  gap: 6px;
  margin: 22px 0;
  overflow-x: auto;
}

.catalog nav button {
  padding: 7px 10px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 12px;
  text-transform: uppercase;
  cursor: pointer;
}

.catalog nav button.active {
  border-color: var(--acid);
  color: var(--acid);
}

.index-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.index-grid article {
  display: grid;
  min-height: 260px;
  gap: 12px;
  align-content: start;
  padding: 18px;
  border: 1px solid var(--border);
  background: linear-gradient(
    150deg,
    color-mix(in srgb, var(--accent) 5%, var(--surface-2)),
    var(--surface-1) 58%
  );
  transition: border-color 180ms ease, transform 180ms ease;
}

.index-grid article:hover {
  border-color: rgba(188, 255, 66, 0.55);
  transform: translateY(-3px);
}

.card-header {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.card-index {
  padding: 5px 7px;
  border: 1px solid var(--border-strong);
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 12px;
}

.card-header strong {
  overflow: hidden;
  color: var(--text-0);
  font-size: 16px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.formula-card {
  display: grid;
  gap: 8px;
  min-height: 72px;
  padding: 11px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--border));
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, transparent), transparent 54%),
    var(--surface-0);
}

.formula-label {
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
}

.formula-line {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
}

.formula-token {
  display: inline-grid;
  min-height: 24px;
  align-items: center;
  padding: 2px 6px;
  border: 1px solid transparent;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.2;
}

.token-band {
  border-color: color-mix(in srgb, var(--acid) 45%, transparent);
  background: color-mix(in srgb, var(--acid) 10%, transparent);
  color: var(--acid);
  font-weight: 700;
}

.token-function {
  border-color: color-mix(in srgb, var(--accent) 38%, transparent);
  color: var(--accent-strong);
}

.token-parameter {
  color: var(--warning);
  font-weight: 700;
}

.token-number {
  color: var(--text-1);
}

.token-operator {
  min-width: 20px;
  padding-inline: 2px;
  color: var(--text-3);
  text-align: center;
}

.index-grid p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}

.index-grid dl {
  display: grid;
  gap: 4px;
  margin: 0;
}

.index-grid dl > div {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  align-items: start;
  gap: 8px;
}

.index-grid dt,
.index-grid dd,
.index-grid small {
  font-size: 12px;
  line-height: 1.5;
}

.index-grid dt {
  color: var(--text-3);
}

.index-grid dd {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin: 0;
  color: var(--text-2);
}

.index-grid dd span {
  padding: 3px 5px;
  background: var(--surface-3);
  color: var(--text-2);
  font-family: var(--font-mono);
  text-transform: uppercase;
}

.index-grid small {
  color: var(--warning);
}

@media (max-width: 700px) {
  .catalog header {
    align-items: stretch;
    flex-direction: column;
  }

  .catalog input {
    width: 100%;
  }

  .index-grid {
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }
}
</style>
