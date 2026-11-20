<template>
  <div class="error-banner" role="alert">
    <span class="error-banner-msg">{{ message }}</span>
    <button v-if="retryable" class="fb" type="button" @click="$emit('retry')">重试</button>
  </div>
</template>

<script setup>
defineProps({
  message: { type: String, required: true },
  retryable: { type: Boolean, default: true },
})
defineEmits(['retry'])
</script>

<style scoped>
.error-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  background: var(--color-danger-soft);
  border-radius: var(--radius-lg);
  padding: 12px 16px;
  margin-bottom: 14px;
}

.error-banner-msg {
  color: var(--color-danger);
  font-size: var(--font-size-sm);
}
</style>
