<template>
  <span class="badge">{{ category }}</span>
</template>

<script setup>
defineProps({
  category: { type: String, required: true },
})
</script>
