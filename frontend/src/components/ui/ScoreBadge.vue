<template>
  <span class="badge" :class="{ 'is-high': score >= 7 }">评分 {{ score }}</span>
</template>

<script setup>
defineProps({
  score: { type: Number, required: true },
})
</script>

<style scoped>
/* 高分条目（≥7，与 digest 入选阈值一致）高亮 */
.is-high {
  background: var(--color-success-soft);
  color: var(--color-success);
}
</style>
