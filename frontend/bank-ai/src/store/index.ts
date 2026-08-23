import { createPinia } from 'pinia'

export const pinia = createPinia()

export { useUserStore } from './user'
export { useModelStore } from './model'
export { useRuleStore } from './rule'
