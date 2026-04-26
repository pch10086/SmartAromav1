<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watchEffect } from 'vue'
import { getJson, postJson, statusWebSocketUrl } from './api/client'

const SCENES = [
  {
    key: '睡前安睡',
    title: '睡前安睡',
    desc: '像夜色慢慢落下，适合把紧绷感一点点放下。',
    accent: 'sleep',
    mood: '夜雾安睡',
  },
  {
    key: '通勤提神',
    title: '通勤提神',
    desc: '轻快而不刺激，让精神慢慢亮起来。',
    accent: 'commute',
    mood: '清醒流动',
  },
  {
    key: '阅读专注',
    title: '阅读专注',
    desc: '保持清晰与稳定，把注意力温柔收拢。',
    accent: 'focus',
    mood: '静定专注',
  },
  {
    key: '静心冥想',
    title: '静心冥想',
    desc: '节奏慢下来，让呼吸与气味一起变轻。',
    accent: 'meditation',
    mood: '沉静内收',
  },
  {
    key: '晨间唤醒',
    title: '晨间唤醒',
    desc: '带一点晨光的暖意，适合开启新的一段状态。',
    accent: 'morning',
    mood: '晨光苏醒',
  },
] as const

const PERSONAS = [
  {
    key: '专业调香师',
    title: '专业调香师',
    desc: '更专业、更克制，强调香气层次与节奏。',
    vibe: '理性陪伴',
  },
  {
    key: '温柔恋人',
    title: '温柔恋人',
    desc: '更柔和、更细腻，像被轻轻照顾着。',
    vibe: '柔软陪伴',
  },
  {
    key: '松弛老友',
    title: '松弛老友',
    desc: '更自然、更轻松，像有人熟悉地陪你聊两句。',
    vibe: '轻松陪伴',
  },
] as const

const DURATION_LEVELS = [
  { key: '速享', title: '速享', desc: '短时快速进入状态' },
  { key: '标准', title: '标准', desc: '平衡、自然、适合大多数情况' },
  { key: '沉浸', title: '沉浸', desc: '更完整地展开这段香气体验' },
] as const

const GENERATING_HINTS = [
  '正在理解你此刻的场景和情绪节奏…',
  '正在组织更适合你的香气层次与扩散顺序…',
  '正在用当前人格语气生成这次香氛说明…',
] as const

const AROMA_LABELS: Record<string, string> = {
  lavender: '薰衣草',
  rose: '玫瑰',
  chamomile: '洋甘菊',
  sandalwood: '檀香',
  citrus: '柑橘',
  mint: '薄荷',
  frankincense: '乳香',
  lemon: '柠檬',
  rosemary: '迷迭香',
}

interface StartPayload {
  scene: string
  persona: string
  duration_level: string
}

interface StatusPayload {
  phase: string
  scene: string | null
  preference: string | null
  persona: string | null
  duration_level: string | null
  plan_name: string | null
  mood_tag: string | null
  opening_line: string | null
  explanation: string | null
  closing_line: string | null
  current_aroma: string | null
  fan_speed: number
  segment_index: number
  segment_count: number
  segment_remaining_sec: number
  total_remaining_sec: number
  error_message: string | null
}

const selectedScene = ref<string>(SCENES[0].key)
const selectedPersona = ref<string>(PERSONAS[1].key)
const selectedDurationLevel = ref<string>(DURATION_LEVELS[1].key)
const status = ref<StatusPayload | null>(null)
const lastAction = ref('')
const wsError = ref('')
const generatingHintIndex = ref(0)

let ws: WebSocket | null = null
let wsShouldReconnect = true
let generatingHintTimer: number | null = null

const phaseLabel: Record<string, string> = {
  idle: '待命中',
  generating: '正在生成方案',
  running: '陪伴运行中',
  paused: '已暂停',
  completed: '已完成',
  stopped: '已停止',
  error: '错误',
}

const phase = computed(() => status.value?.phase ?? 'idle')
const isGenerating = computed(() => phase.value === 'generating')
const isRunningLike = computed(() => ['running', 'paused'].includes(phase.value))
const isIdleLike = computed(() => !isGenerating.value && !isRunningLike.value)
const canStart = computed(() => !['generating', 'running', 'paused'].includes(phase.value))
const canPause = computed(() => phase.value === 'running')
const canResume = computed(() => phase.value === 'paused')
const canStop = computed(() => ['generating', 'running', 'paused'].includes(phase.value))

const currentSceneMeta = computed(() => {
  const current = status.value?.scene ?? selectedScene.value
  return SCENES.find((item) => item.key === current) ?? SCENES[0]
})

const currentPersonaMeta = computed(() => {
  const current = status.value?.persona ?? selectedPersona.value
  return PERSONAS.find((item) => item.key === current) ?? PERSONAS[0]
})

const currentDurationMeta = computed(() => {
  const current = status.value?.duration_level ?? selectedDurationLevel.value
  return DURATION_LEVELS.find((item) => item.key === current) ?? DURATION_LEVELS[0]
})

const sceneThemeClass = computed(() => `theme-${currentSceneMeta.value.accent}`)
const generatingHint = computed(() => GENERATING_HINTS[generatingHintIndex.value % GENERATING_HINTS.length])
const cleanedExplanation = computed(() => {
  const raw = status.value?.explanation ?? ''
  return raw.replace(/^MOCK_PLAN:\s*/u, '').trim()
})
const persistentFeedback = computed(() => {
  if (status.value?.error_message) return status.value.error_message
  if (wsError.value) return wsError.value
  return ''
})
const progressText = computed(() => {
  if (!status.value || status.value.segment_count <= 0) return '等待方案生成'
  return `${Math.max(0, status.value.segment_index) + 1} / ${status.value.segment_count}`
})

function formatMmSs(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

function aromaLabel(id: string | null): string {
  if (!id) return '—'
  return AROMA_LABELS[id] ?? id
}

function startGeneratingHints() {
  stopGeneratingHints()
  generatingHintIndex.value = 0
  generatingHintTimer = window.setInterval(() => {
    generatingHintIndex.value = (generatingHintIndex.value + 1) % GENERATING_HINTS.length
  }, 2200)
}

function stopGeneratingHints() {
  if (generatingHintTimer !== null) {
    window.clearInterval(generatingHintTimer)
    generatingHintTimer = null
  }
}

function connectWs() {
  wsError.value = ''
  ws = new WebSocket(statusWebSocketUrl())
  ws.onmessage = (ev) => {
    try {
      status.value = JSON.parse(ev.data) as StatusPayload
    } catch {
      wsError.value = '无法解析状态数据'
    }
  }
  ws.onerror = () => {
    wsError.value = 'WebSocket 连接异常（请确认后端已启动）'
  }
  ws.onclose = () => {
    if (!wsShouldReconnect) return
    if (wsError.value === '') wsError.value = '连接已断开，正在重试…'
    setTimeout(() => {
      if (wsShouldReconnect) connectWs()
    }, 2000)
  }
}

async function refreshOnce() {
  try {
    status.value = await getJson<StatusPayload>('/api/state')
    lastAction.value = ''
  } catch {
    lastAction.value = '无法拉取状态，请启动后端'
  }
}

async function onStart() {
  const payload: StartPayload = {
    scene: selectedScene.value,
    persona: selectedPersona.value,
    duration_level: selectedDurationLevel.value,
  }
  try {
    const response = await postJson<{ ok: boolean; message: string }>('/api/start', payload)
    lastAction.value = response.message
  } catch (error) {
    lastAction.value = error instanceof Error ? error.message : String(error)
  }
}

async function onPause() {
  try {
    const response = await postJson<{ ok: boolean; message: string }>('/api/pause')
    lastAction.value = response.message
  } catch (error) {
    lastAction.value = error instanceof Error ? error.message : String(error)
  }
}

async function onResume() {
  try {
    const response = await postJson<{ ok: boolean; message: string }>('/api/resume')
    lastAction.value = response.message
  } catch (error) {
    lastAction.value = error instanceof Error ? error.message : String(error)
  }
}

async function onStop() {
  try {
    const response = await postJson<{ ok: boolean; message: string }>('/api/stop')
    lastAction.value = response.message
  } catch (error) {
    lastAction.value = error instanceof Error ? error.message : String(error)
  }
}

onMounted(() => {
  void refreshOnce()
  connectWs()
})

onUnmounted(() => {
  wsShouldReconnect = false
  stopGeneratingHints()
  if (ws) {
    ws.onclose = null
    ws.close()
  }
})

const stopGenerating = computed(() => !isGenerating.value)

watchEffect(() => {
  if (isGenerating.value) {
    startGeneratingHints()
  }
  if (stopGenerating.value) {
    stopGeneratingHints()
  }
})
</script>

<template>
  <div class="app-shell" :class="sceneThemeClass">
    <div class="mist mist-1" />
    <div class="mist mist-2" />
    <div class="mist mist-3" />

    <main class="app-frame">
      <header class="brand-row">
        <div>
          <p class="brand-mark">SmartAroma</p>
          <h1 class="brand-title">小屏智能香氛伴侣</h1>
        </div>
        <span class="phase-pill">{{ phaseLabel[phase] ?? phase }}</span>
      </header>

      <Transition name="view-fade" mode="out-in">
        <section v-if="isIdleLike" class="idle-view" key="idle">
        <article class="hero-card soft-card">
          <div class="hero-copy">
            <p class="hero-tag">{{ currentSceneMeta.mood }}</p>
            <h2>{{ currentSceneMeta.title }}</h2>
            <p class="hero-desc">{{ currentSceneMeta.desc }}</p>
            <p class="hero-support">
              选择一个此刻更贴近你的场景，让香气与角色语气一起，把状态温柔地带到合适的位置。
            </p>
          </div>
          <div class="hero-orb" />
        </article>

        <section class="composer-grid">
          <article class="soft-card section-card scene-section">
            <div class="section-head">
              <div>
                <p class="section-eyebrow">Scene</p>
                <h3>选择场景</h3>
              </div>
              <span class="section-note">主选择项</span>
            </div>
            <div class="scene-stack">
              <button
                v-for="scene in SCENES"
                :key="scene.key"
                type="button"
                class="scene-option"
                :class="{ active: selectedScene === scene.key }"
                :disabled="!canStart"
                @click="selectedScene = scene.key"
              >
                <span class="scene-option-title">{{ scene.title }}</span>
                <span class="scene-option-desc">{{ scene.desc }}</span>
              </button>
            </div>
          </article>

          <article class="soft-card section-card option-section">
            <div class="section-head compact-head">
              <div>
                <p class="section-eyebrow">Persona</p>
                <h3>角色人格</h3>
              </div>
              <span class="section-note">辅助选择</span>
            </div>
            <div class="persona-stack">
              <button
                v-for="persona in PERSONAS"
                :key="persona.key"
                type="button"
                class="persona-option"
                :class="{ active: selectedPersona === persona.key }"
                :disabled="!canStart"
                @click="selectedPersona = persona.key"
              >
                <span class="persona-title">{{ persona.title }}</span>
                <span class="persona-desc">{{ persona.desc }}</span>
                <span class="persona-vibe">{{ persona.vibe }}</span>
              </button>
            </div>

            <div class="section-head compact-head duration-head">
              <div>
                <p class="section-eyebrow">Duration</p>
                <h3>时长档位</h3>
              </div>
            </div>
            <div class="duration-row">
              <button
                v-for="duration in DURATION_LEVELS"
                :key="duration.key"
                type="button"
                class="duration-option"
                :class="{ active: selectedDurationLevel === duration.key }"
                :disabled="!canStart"
                @click="selectedDurationLevel = duration.key"
              >
                <span class="duration-title">{{ duration.title }}</span>
                <span class="duration-desc">{{ duration.desc }}</span>
              </button>
            </div>
          </article>
        </section>

        <article class="soft-card action-card">
          <div class="action-copy">
            <p class="action-label">即将生成</p>
            <h3>{{ currentSceneMeta.title }} · {{ currentPersonaMeta.title }}</h3>
            <p>{{ currentDurationMeta.desc }}</p>
          </div>
          <button type="button" class="primary-action" :disabled="!canStart" @click="onStart">
            生成今天的香氛陪伴
          </button>
        </article>
      </section>

        <section v-else-if="isGenerating" class="generating-view soft-card" key="generating">
        <div class="generating-orbit">
          <div class="pulse pulse-outer" />
          <div class="pulse pulse-inner" />
          <div class="pulse-core" />
        </div>

        <div class="generating-copy">
          <p class="section-eyebrow">Composing</p>
          <h2>{{ selectedScene }}</h2>
          <p class="generating-hint">{{ generatingHint }}</p>
          <div class="generating-meta">
            <span class="meta-pill">{{ selectedPersona }}</span>
            <span class="meta-pill">{{ selectedDurationLevel }}</span>
          </div>
        </div>

        <div class="floating-note-row">
          <span class="floating-note">正在组织香气层次</span>
          <span class="floating-note">正在匹配角色语气</span>
          <span class="floating-note">正在生成结构化计划</span>
        </div>

        <div class="control-row centered">
          <button type="button" class="secondary-action danger" :disabled="!canStop" @click="onStop">
            取消本次生成
          </button>
        </div>
        </section>

        <section v-else class="running-view" key="running">
        <article class="hero-card running-hero soft-card">
          <div class="hero-copy">
            <p class="hero-tag">{{ status?.mood_tag || currentSceneMeta.mood }}</p>
            <h2>{{ status?.plan_name || currentSceneMeta.title }}</h2>
            <p class="hero-desc">{{ status?.opening_line || currentSceneMeta.desc }}</p>
          </div>
          <div class="hero-mini-meta">
            <span class="meta-pill">{{ status?.scene || selectedScene }}</span>
            <span class="meta-pill">{{ status?.persona || selectedPersona }}</span>
            <span class="meta-pill">{{ status?.duration_level || selectedDurationLevel }}</span>
          </div>
        </article>

        <section class="running-grid">
          <article class="soft-card monitor-card main-monitor">
            <div class="monitor-top">
              <div>
                <p class="section-eyebrow">Current</p>
                <h3>{{ aromaLabel(status?.current_aroma ?? null) }}</h3>
              </div>
              <span class="live-dot" />
            </div>
            <div class="countdown-row">
              <div>
                <span class="metric-label">本段剩余</span>
                <strong>{{ formatMmSs(status?.segment_remaining_sec ?? 0) }}</strong>
              </div>
              <div>
                <span class="metric-label">总剩余</span>
                <strong>{{ formatMmSs(status?.total_remaining_sec ?? 0) }}</strong>
              </div>
            </div>
            <div class="progress-block">
              <div class="progress-text-row">
                <span>{{ progressText }}</span>
                <span>{{ status?.fan_speed ?? 0 }}%</span>
              </div>
              <progress class="progress-bar" max="100" :value="status?.fan_speed ?? 0" />
            </div>
          </article>

          <article class="soft-card monitor-card info-card">
            <p class="section-eyebrow">Runtime</p>
            <div class="info-list">
              <div class="info-item">
                <span class="metric-label">阶段</span>
                <strong>{{ phaseLabel[phase] ?? phase }}</strong>
              </div>
              <div class="info-item">
                <span class="metric-label">偏好映射</span>
                <strong>{{ status?.preference ?? '—' }}</strong>
              </div>
              <div class="info-item">
                <span class="metric-label">角色人格</span>
                <strong>{{ status?.persona ?? selectedPersona }}</strong>
              </div>
            </div>
          </article>
        </section>

        <article class="soft-card story-card">
          <div class="story-head">
            <div>
              <p class="section-eyebrow">Reason</p>
              <h3>香气理由</h3>
            </div>
            <span class="story-role">{{ status?.persona ?? selectedPersona }}</span>
          </div>
          <p class="story-main">{{ cleanedExplanation || '本次香氛说明会显示在这里。' }}</p>
          <div v-if="status?.closing_line" class="story-footer">
            <span class="story-divider" />
            <p class="story-closing">{{ status.closing_line }}</p>
          </div>
        </article>

        <div class="control-row">
          <button type="button" class="primary-action subtle" :disabled="!canPause" @click="onPause">暂停</button>
          <button type="button" class="primary-action subtle" :disabled="!canResume" @click="onResume">恢复</button>
          <button type="button" class="secondary-action danger" :disabled="!canStop" @click="onStop">终止</button>
        </div>
      </section>
      </Transition>

      <section v-if="persistentFeedback" class="feedback-panel soft-card">
        <p v-if="status?.error_message" class="feedback error">{{ persistentFeedback }}</p>
        <p v-else-if="wsError" class="feedback warn">{{ persistentFeedback }}</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  --bg-main: #110f1c;
  --bg-top: #171124;
  --bg-bottom: #0b0913;
  --mist-highlight: rgba(255, 255, 255, 0.14);
  --mist-secondary: rgba(255, 255, 255, 0.1);
  --panel-bg: rgba(255, 255, 255, 0.12);
  --panel-border: rgba(255, 255, 255, 0.18);
  --text-main: #fffaf8;
  --text-soft: rgba(255, 250, 248, 0.74);
  --accent: #b89cff;
  --accent-soft: rgba(184, 156, 255, 0.22);
  --accent-strong: #dbcdfd;
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  color: var(--text-main);
  background:
    radial-gradient(circle at 18% 16%, var(--mist-highlight), transparent 22%),
    radial-gradient(circle at 80% 12%, var(--mist-secondary), transparent 24%),
    linear-gradient(180deg, var(--bg-top) 0%, var(--bg-main) 58%, var(--bg-bottom) 100%);
  transition:
    background 0.8s ease,
    color 0.45s ease;
}

.theme-sleep {
  --bg-top: #221738;
  --bg-main: #120f22;
  --bg-bottom: #080611;
  --mist-highlight: rgba(233, 220, 255, 0.2);
  --mist-secondary: rgba(201, 177, 255, 0.12);
  --accent: #b79cf7;
  --accent-soft: rgba(183, 156, 247, 0.3);
  --accent-strong: #d8cdfa;
}

.theme-commute {
  --bg-top: #3a2318;
  --bg-main: #1f1611;
  --bg-bottom: #0d0907;
  --mist-highlight: rgba(255, 219, 180, 0.22);
  --mist-secondary: rgba(255, 194, 126, 0.14);
  --accent: #f2b46d;
  --accent-soft: rgba(242, 180, 109, 0.3);
  --accent-strong: #ffe0b8;
}

.theme-focus {
  --bg-top: #173127;
  --bg-main: #101d18;
  --bg-bottom: #090d0b;
  --mist-highlight: rgba(220, 255, 238, 0.16);
  --mist-secondary: rgba(149, 208, 182, 0.14);
  --accent: #95d0b6;
  --accent-soft: rgba(149, 208, 182, 0.26);
  --accent-strong: #d9f2e7;
}

.theme-meditation {
  --bg-top: #152438;
  --bg-main: #0f1621;
  --bg-bottom: #070b11;
  --mist-highlight: rgba(221, 236, 255, 0.18);
  --mist-secondary: rgba(145, 184, 234, 0.14);
  --accent: #91b8ea;
  --accent-soft: rgba(145, 184, 234, 0.28);
  --accent-strong: #d8e8fb;
}

.theme-morning {
  --bg-top: #3b211f;
  --bg-main: #211414;
  --bg-bottom: #0f0a0b;
  --mist-highlight: rgba(255, 231, 225, 0.2);
  --mist-secondary: rgba(244, 166, 162, 0.14);
  --accent: #f4a6a2;
  --accent-soft: rgba(244, 166, 162, 0.28);
  --accent-strong: #ffd7d3;
}

.mist {
  position: absolute;
  border-radius: 999px;
  filter: blur(60px);
  opacity: 0.48;
  pointer-events: none;
  animation: drift 14s ease-in-out infinite;
  transition:
    background 0.85s ease,
    opacity 0.6s ease,
    transform 0.8s ease;
}

.mist-1 {
  width: 260px;
  height: 260px;
  top: 32px;
  left: -30px;
  background: var(--accent-soft);
}

.mist-2 {
  width: 320px;
  height: 320px;
  top: 140px;
  right: -80px;
  background: var(--mist-highlight);
  animation-delay: -3s;
}

.mist-3 {
  width: 220px;
  height: 220px;
  bottom: 90px;
  left: 20%;
  background: color-mix(in srgb, var(--accent-soft) 70%, white 30%);
  animation-delay: -7s;
}

.app-frame {
  position: relative;
  z-index: 1;
  max-width: 760px;
  margin: 0 auto;
  padding: 1rem 0.95rem 2.2rem;
}

.brand-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
  margin-bottom: 1rem;
}

.brand-mark,
.section-eyebrow,
.hero-tag,
.action-label {
  margin: 0;
  font-size: 0.74rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent-strong);
}

.brand-title {
  margin: 0.4rem 0 0;
  font-size: 1.55rem;
  font-weight: 700;
}

.phase-pill,
.meta-pill,
.section-note {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 0.85rem;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-main);
  backdrop-filter: blur(12px);
}

.phase-pill {
  white-space: nowrap;
}

.soft-card {
  position: relative;
  overflow: hidden;
  border-radius: 28px;
  border: 1px solid var(--panel-border);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.17), rgba(255, 255, 255, 0.08)),
    var(--panel-bg);
  backdrop-filter: blur(18px);
  box-shadow:
    0 18px 50px rgba(7, 5, 14, 0.28),
    0 0 0 1px rgba(255, 255, 255, 0.04) inset,
    0 0 42px color-mix(in srgb, var(--accent-soft) 45%, transparent 55%);
  transition:
    border-color 0.55s ease,
    box-shadow 0.7s ease,
    background 0.7s ease,
    transform 0.35s ease;
}

.soft-card::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08), transparent 42%);
  pointer-events: none;
  transition: background 0.6s ease;
}


.idle-view,
.running-view {
  display: grid;
  gap: 1rem;
}

.hero-card {
  display: grid;
  grid-template-columns: 1.35fr 0.65fr;
  gap: 1rem;
  padding: 1.2rem;
  min-height: 240px;
}

.hero-copy {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.hero-copy h2 {
  margin: 0.45rem 0 0;
  font-size: 2rem;
  line-height: 1.05;
}

.hero-desc {
  margin: 0.8rem 0 0;
  font-size: 1rem;
  line-height: 1.7;
}

.hero-support {
  margin: 1rem 0 0;
  max-width: 34rem;
  color: var(--text-soft);
  line-height: 1.7;
}

.hero-orb,
.generating-orbit {
  display: flex;
  align-items: center;
  justify-content: center;
}

.hero-orb::before {
  content: '';
  width: 220px;
  height: 220px;
  border-radius: 999px;
  background:
    radial-gradient(circle at 35% 30%, rgba(255, 255, 255, 0.55), transparent 25%),
    radial-gradient(circle at 50% 50%, var(--accent-soft), transparent 58%),
    radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.08), transparent 78%);
  box-shadow:
    inset 0 0 30px rgba(255, 255, 255, 0.16),
    0 0 44px color-mix(in srgb, var(--accent-soft) 65%, transparent 35%);
  animation: breathe 6.5s ease-in-out infinite;
  transition:
    background 0.75s ease,
    box-shadow 0.75s ease,
    transform 0.75s ease;
}

.composer-grid,
.running-grid {
  display: grid;
  gap: 1rem;
}

.composer-grid {
  grid-template-columns: 1.2fr 0.95fr;
}

.running-grid {
  grid-template-columns: 1.1fr 0.9fr;
}

.section-card,
.monitor-card,
.story-card,
.action-card,
.generating-view,
.feedback-panel {
  padding: 1rem;
}

.story-head {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: flex-start;
  margin-bottom: 0.9rem;
}

.story-head h3 {
  margin: 0.35rem 0 0;
  font-size: 1.08rem;
}

.story-role {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 0.8rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: var(--text-soft);
  font-size: 0.82rem;
}

.section-head,
.monitor-top {
  position: relative;
  z-index: 1;
  display: flex;
  justify-content: space-between;
  gap: 0.8rem;
  align-items: flex-start;
  margin-bottom: 0.9rem;
}

.compact-head {
  margin-bottom: 0.7rem;
}

.section-head h3,
.monitor-top h3,
.action-card h3 {
  margin: 0.35rem 0 0;
  font-size: 1.1rem;
}

.scene-stack,
.persona-stack,
.duration-row,
.info-list {
  display: grid;
  gap: 0.7rem;
}

.scene-option,
.persona-option,
.duration-option,
.primary-action,
.secondary-action {
  position: relative;
  z-index: 1;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-main);
  transition:
    transform 0.2s ease,
    border-color 0.2s ease,
    background 0.2s ease,
    box-shadow 0.2s ease;
}

.scene-option,
.persona-option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.35rem;
  min-height: 94px;
  padding: 0.95rem;
  border-radius: 22px;
  text-align: left;
}

.duration-row {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.duration-option {
  min-height: 98px;
  padding: 0.8rem 0.65rem;
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.35rem;
  text-align: center;
}

.scene-option.active,
.persona-option.active,
.duration-option.active {
  border-color: rgba(255, 255, 255, 0.34);
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.08));
  box-shadow: 0 12px 28px rgba(5, 4, 10, 0.16);
}

.scene-option-title,
.persona-title,
.duration-title {
  font-size: 1rem;
  font-weight: 700;
}

.scene-option-desc,
.persona-desc,
.duration-desc,
.persona-vibe,
.story-closing,
.feedback,
.section-note {
  color: var(--text-soft);
}

.persona-vibe {
  font-size: 0.8rem;
}

.action-card {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
}

.action-copy p {
  margin: 0.45rem 0 0;
  color: var(--text-soft);
}

.primary-action,
.secondary-action {
  min-height: 54px;
  padding: 0 1.1rem;
  border-radius: 999px;
  font-size: 0.98rem;
  font-weight: 700;
}

.primary-action {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.92), var(--accent-strong));
  color: #120f1f;
  border-color: transparent;
}

.primary-action.subtle {
  background: rgba(255, 255, 255, 0.12);
  color: var(--text-main);
  border-color: rgba(255, 255, 255, 0.14);
}

.secondary-action.danger {
  border-color: rgba(255, 210, 210, 0.32);
}

.generating-view {
  min-height: 72vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  gap: 1.2rem;
}

.generating-orbit {
  position: relative;
  width: 220px;
  height: 220px;
}

.pulse,
.pulse-core {
  position: absolute;
  inset: 50%;
  transform: translate(-50%, -50%);
  border-radius: 999px;
}

.pulse-outer {
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, var(--accent-soft), transparent 68%);
  animation: breathe 4.6s ease-in-out infinite;
}

.pulse-inner {
  width: 150px;
  height: 150px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(12px);
  animation: breathe 3.2s ease-in-out infinite;
}

.pulse-core {
  width: 64px;
  height: 64px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), var(--accent-strong));
  box-shadow: 0 0 40px var(--accent-soft);
}

.generating-copy h2 {
  margin: 0.45rem 0 0;
  font-size: 2rem;
}

.generating-hint {
  margin: 0.8rem 0 0;
  min-height: 3.4rem;
  font-size: 1rem;
  line-height: 1.7;
  color: var(--text-soft);
}

.generating-meta,
.floating-note-row,
.hero-mini-meta,
.control-row,
.countdown-row,
.progress-text-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.floating-note-row {
  justify-content: center;
}

.floating-note {
  min-height: 34px;
  padding: 0 0.9rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  color: var(--text-soft);
}

.centered {
  justify-content: center;
}

.running-hero {
  grid-template-columns: 1fr;
  min-height: unset;
}

.hero-mini-meta {
  margin-top: 1rem;
}

.main-monitor h3 {
  font-size: 1.65rem;
}

.live-dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: var(--accent-strong);
  box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.4);
  animation: ping 2.2s ease-out infinite;
}

.countdown-row {
  justify-content: space-between;
  margin-top: 0.9rem;
}

.metric-label {
  display: block;
  font-size: 0.76rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-soft);
  margin-bottom: 0.28rem;
}

.countdown-row strong,
.info-item strong {
  font-size: 1.25rem;
}

.progress-block {
  margin-top: 1rem;
}

.progress-text-row {
  justify-content: space-between;
  font-size: 0.92rem;
  color: var(--text-soft);
  margin-bottom: 0.45rem;
}

.progress-bar {
  width: 100%;
  height: 12px;
  accent-color: var(--accent);
}

.info-list {
  margin-top: 0.6rem;
}

.story-main {
  margin: 0;
  line-height: 1.95;
  font-size: 1.06rem;
  letter-spacing: 0.01em;
}

.story-footer {
  margin-top: 1rem;
}

.story-divider {
  display: block;
  width: 100%;
  height: 1px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0));
}

.story-closing {
  margin: 0.85rem 0 0;
  line-height: 1.75;
  color: var(--text-soft);
  font-size: 0.95rem;
}

.control-row {
  justify-content: flex-start;
}

.feedback-panel {
  padding: 0.95rem 1rem;
}

.feedback {
  margin: 0;
  line-height: 1.65;
}

.feedback + .feedback {
  margin-top: 0.45rem;
}

.feedback.error {
  color: #ffd2d2;
}

.feedback.warn {
  color: #fce7b2;
}

.scene-option:disabled,
.persona-option:disabled,
.duration-option:disabled,
.primary-action:disabled,
.secondary-action:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.scene-option:not(:disabled):hover,
.persona-option:not(:disabled):hover,
.duration-option:not(:disabled):hover,
.primary-action:not(:disabled):hover,
.secondary-action:not(:disabled):hover {
  transform: translateY(-1px);
}

@keyframes drift {
  0%,
  100% {
    transform: translate3d(0, 0, 0) scale(1);
  }
  50% {
    transform: translate3d(10px, -14px, 0) scale(1.06);
  }
}

@keyframes breathe {
  0%,
  100% {
    transform: translate(-50%, -50%) scale(0.96);
    opacity: 0.78;
  }
  50% {
    transform: translate(-50%, -50%) scale(1.04);
    opacity: 1;
  }
}

@keyframes ping {
  0% {
    box-shadow: 0 0 0 0 rgba(255, 255, 255, 0.35);
  }
  70% {
    box-shadow: 0 0 0 12px rgba(255, 255, 255, 0);
  }
  100% {
    box-shadow: 0 0 0 0 rgba(255, 255, 255, 0);
  }
}

.view-fade-enter-active,
.view-fade-leave-active {
  transition:
    opacity 0.35s ease,
    transform 0.35s ease,
    filter 0.35s ease;
}

.view-fade-enter-from,
.view-fade-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.99);
  filter: blur(6px);
}

@media (max-width: 720px) {
  .brand-row,
  .section-head,
  .action-card,
  .hero-card,
  .composer-grid,
  .running-grid,
  .countdown-row,
  .control-row {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: flex-start;
  }

  .hero-card,
  .composer-grid,
  .running-grid {
    display: grid;
  }

  .duration-row {
    grid-template-columns: 1fr;
  }

  .app-frame {
    padding: 0.95rem 0.85rem 2rem;
  }

  .hero-copy h2,
  .generating-copy h2 {
    font-size: 1.65rem;
  }

  .primary-action,
  .secondary-action {
    width: 100%;
  }
}
</style>
