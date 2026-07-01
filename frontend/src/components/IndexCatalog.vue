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
interface FormulaFraction {
  numerator: FormulaToken[]
  denominator: FormulaToken[]
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

function matchingOuterParens(expression: string) {
  if (!expression.startsWith('(') || !expression.endsWith(')')) return false
  let depth = 0
  for (let index = 0; index < expression.length; index += 1) {
    const char = expression[index]
    if (char === '(') depth += 1
    if (char === ')') depth -= 1
    if (depth === 0 && index < expression.length - 1) return false
  }
  return depth === 0
}

function stripOuterParens(expression: string): string {
  let current = expression.trim()
  while (matchingOuterParens(current)) {
    current = current.slice(1, -1).trim()
  }
  return current
}

function splitTopLevelDivision(formula: string): [string, string] | null {
  let depth = 0
  for (let index = 0; index < formula.length; index += 1) {
    const char = formula[index]
    if (char === '(') depth += 1
    if (char === ')') depth -= 1
    if (char === '/' && depth === 0) {
      return [formula.slice(0, index), formula.slice(index + 1)]
    }
  }
  return null
}

function fractionFormula(formula: string): FormulaFraction | null {
  // 只拆最外层除号，避免把 sqrt(...) 或括号内部表达式误渲染成错误分式。
  const parts = splitTopLevelDivision(formula)
  if (!parts) return null
  return {
    numerator: tokenizeFormula(stripOuterParens(parts[0])),
    denominator: tokenizeFormula(stripOuterParens(parts[1])),
  }
}

function tokenLabel(token: FormulaToken) {
  return token.value === '*' ? '×' : token.value
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
          <div v-if="fractionFormula(item.formula)" class="formula-fraction">
            <div class="formula-row numerator">
              <span
                v-for="(token, tokenIndex) in fractionFormula(item.formula)?.numerator"
                :key="`${item.id}-num-${tokenIndex}-${token.value}`"
                class="formula-symbol"
                :class="`symbol-${token.type}`"
              >
                {{ tokenLabel(token) }}
              </span>
            </div>
            <div class="fraction-rule" />
            <div class="formula-row denominator">
              <span
                v-for="(token, tokenIndex) in fractionFormula(item.formula)?.denominator"
                :key="`${item.id}-den-${tokenIndex}-${token.value}`"
                class="formula-symbol"
                :class="`symbol-${token.type}`"
              >
                {{ tokenLabel(token) }}
              </span>
            </div>
          </div>
          <div v-else class="formula-row formula-inline">
            <span
              v-for="(token, tokenIndex) in tokenizeFormula(item.formula)"
              :key="`${item.id}-${tokenIndex}-${token.value}`"
              class="formula-symbol"
              :class="`symbol-${token.type}`"
            >
              {{ tokenLabel(token) }}
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
  min-height: 86px;
  place-items: center;
  gap: 6px;
  padding: 12px 14px;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--accent) 42%, var(--border));
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--accent) 6%, transparent), transparent 64%),
    var(--surface-0);
}

.formula-label {
  justify-self: start;
  color: var(--acid);
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 700;
}

.formula-fraction {
  display: inline-grid;
  min-width: min(100%, 150px);
  justify-items: center;
}

.formula-row {
  display: inline-flex;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 2px;
}

.formula-inline {
  min-height: 42px;
}

.formula-symbol {
  display: inline-block;
  padding: 0 2px;
  color: var(--text-1);
  font-family: Georgia, "Times New Roman", serif;
  font-size: 18px;
  font-style: italic;
  line-height: 1.28;
}

.fraction-rule {
  width: 100%;
  min-width: 92px;
  height: 1px;
  margin: 3px 0;
  background: color-mix(in srgb, var(--text-1) 72%, transparent);
}

.symbol-band {
  color: var(--acid);
  font-weight: 700;
}

.symbol-function {
  color: var(--accent-strong);
  font-style: normal;
}

.symbol-parameter {
  color: var(--warning);
  font-weight: 700;
}

.symbol-number {
  color: var(--text-1);
  font-style: normal;
}

.symbol-operator {
  min-width: 12px;
  color: var(--text-3);
  text-align: center;
  font-style: normal;
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
