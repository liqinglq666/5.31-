<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted, nextTick } from 'vue'

interface NavItem {
  id: string
  label: string
}

const props = defineProps<{
  activeTab: string
}>()

const emit = defineEmits<{
  (e: 'switch-tab', tab: string): void
}>()

const activeId = ref('')

const allNavItems: NavItem[] = [
  { id: 'section-score', label: '合规评分' },
  { id: 'section-risk', label: '核心风险' },
  { id: 'section-finance', label: '财务视图' },
  { id: 'section-history', label: 'RAG 溯源' },
  { id: 'section-audit', label: '审计留痕' },
]

const visibleItems = computed(() => {
  if (props.activeTab === 'financial') {
    return allNavItems.filter((i) => i.id === 'section-finance')
  }
  return allNavItems.filter((i) => i.id !== 'section-finance')
})

let observer: IntersectionObserver | null = null

const observeSections = () => {
  if (observer) {
    observer.disconnect()
    observer = null
  }

  const ids = visibleItems.value.map((i) => i.id)
  const elements = ids
    .map((id) => document.getElementById(id))
    .filter(Boolean) as HTMLElement[]

  if (elements.length === 0) return

  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          activeId.value = entry.target.id
        }
      })
    },
    {
      rootMargin: '-10% 0px -80% 0px',
      threshold: 0,
    },
  )

  elements.forEach((el) => observer!.observe(el))
}

watch(
  () => props.activeTab,
  () => {
    activeId.value = ''
    nextTick(() => observeSections())
  },
)

onMounted(() => {
  observeSections()
})

onUnmounted(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }
})

const scrollToSection = (id: string) => {
  if (id === 'section-finance' && props.activeTab !== 'financial') {
    emit('switch-tab', 'financial')
    nextTick(() => {
      setTimeout(() => {
        const el = document.getElementById(id)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      }, 100)
    })
    return
  }

  if (props.activeTab !== 'compliance' && id !== 'section-finance') {
    emit('switch-tab', 'compliance')
    nextTick(() => {
      setTimeout(() => {
        const el = document.getElementById(id)
        if (el) {
          el.scrollIntoView({ behavior: 'smooth', block: 'start' })
        }
      }, 100)
    })
    return
  }

  const el = document.getElementById(id)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<template>
  <nav v-if="visibleItems.length" class="report-anchor">
    <div class="anchor-line" />
    <ul class="anchor-list">
      <li
        v-for="item in visibleItems"
        :key="item.id"
        class="anchor-item"
        :class="{ active: activeId === item.id }"
        @click="scrollToSection(item.id)"
      >
        {{ item.label }}
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.report-anchor {
  position: fixed;
  right: 24px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 50;
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  border-radius: 8px;
  padding: 12px 0;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
}

.anchor-line {
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 1px;
  background: #e2e8f0;
}

.anchor-list {
  list-style: none;
  margin: 0;
  padding: 0;
  position: relative;
}

.anchor-item {
  position: relative;
  padding: 8px 16px 8px 20px;
  font-size: 13px;
  color: #64748b;
  cursor: pointer;
  transition: color 0.2s ease;
  white-space: nowrap;
  user-select: none;
}

.anchor-item:hover {
  color: #334155;
}

.anchor-item.active {
  color: #2563eb;
  font-weight: 600;
}

.anchor-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 16px;
  background: #2563eb;
  border-radius: 0 2px 2px 0;
}
</style>
