<template>
  <button v-if="!confirming" class="fb" type="button" @click="confirming = true">删除</button>
  <span v-else class="confirm-row">
    <button class="fb confirm-del" type="button" @click="onConfirm">确认删除</button>
    <button class="fb" type="button" @click="reset">取消</button>
  </span>
</template>

<script setup>
import { ref, watch, onUnmounted } from 'vue'

/**
 * 逻辑删除入口（web-frontend-plan §3.7）：
 * 两段式确认防误触；确认态 3s 无操作自动复原，避免挂起。
 * 本组件只 emit('confirm')，删除请求与失败回滚由父级处理。
 */
const emit = defineEmits(['confirm'])

const confirming = ref(false)
let timer = null

function clearTimer() {
  if (timer) {
    clearTimeout(timer)
    timer = null
  }
}

function reset() {
  confirming.value = false
  clearTimer()
}

function onConfirm() {
  emit('confirm')
  reset()
}

watch(confirming, (active) => {
  clearTimer()
  if (active) {
    timer = setTimeout(reset, 3000)
  }
})

onUnmounted(clearTimer)
</script>

<style scoped>
.confirm-row {
  display: inline-flex;
  gap: 6px;
}

.confirm-del {
  color: var(--color-danger);
  border-color: var(--color-danger);
}
</style>
