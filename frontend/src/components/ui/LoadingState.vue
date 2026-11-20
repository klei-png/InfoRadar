<template>
  <div class="skeleton-group" aria-busy="true">
    <div v-for="i in rows" :key="i" class="skeleton" :class="{ short: i === rows }"></div>
  </div>
</template>

<script setup>
defineProps({
  rows: { type: Number, default: 3 },
})
</script>

<style scoped>
.skeleton {
  height: 14px;
  border-radius: var(--radius-sm);
  background: linear-gradient(
    90deg,
    var(--color-hover) 25%,
    var(--color-surface) 50%,
    var(--color-hover) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.2s infinite;
  margin-bottom: 10px;
}

.skeleton.short {
  width: 60%;
  margin-bottom: 0;
}

@keyframes shimmer {
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}
</style>
