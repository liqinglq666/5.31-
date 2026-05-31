<template>
  <router-view />
  <!-- 全局防泄密水印：仅登录成功后显示 -->
  <Watermark />
</template>

<script setup lang="ts">
import Watermark from '@/components/Watermark.vue'
</script>

<style>
/* 移动端全局兜底：防止内容溢出导致浏览器自动缩放 */
@media (max-width: 768px) {
  html, body {
    overflow-x: hidden;
  }
}
</style>
