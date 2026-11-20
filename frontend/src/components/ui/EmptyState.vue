<template>
  <p class="empty">{{ text }}</p>
</template>

<script setup>
defineProps({
  text: { type: String, default: '暂无数据' },
})
</script>
