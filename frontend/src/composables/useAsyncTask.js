import { ref, onUnmounted, getCurrentInstance } from 'vue'

const isAbortError = (err) => err?.name === 'AbortError'

/**
 * 三态异步任务包装（web-frontend-plan §3.3）。
 *
 * 约定：taskFn 的第一个参数是本次任务的 AbortSignal，业务侧必须把它传给请求层。
 *
 * - run(...args)：触发任务；进行中再触发会**取消旧任务**（旧结果不得覆盖新结果）
 * - retry()：复用最近一次 run 的参数重试
 * - cancel()：主动取消；取消（AbortError）不展示为错误，结果不写入
 * - 组件卸载时自动取消在途任务
 *
 * 返回值：run/retry 返回任务结果；已取消、被新任务取代或失败时返回 undefined，
 * 失败详情经 error 状态承载。所有状态写入都经 seq 守卫，只允许最新任务落盘。
 */
export function useAsyncTask(taskFn) {
  const loading = ref(false)
  const error = ref(null)
  const data = ref(null)

  let seq = 0
  let controller = null
  let lastArgs = null
  let disposed = false

  function abortInFlight() {
    if (controller && !controller.signal.aborted) {
      controller.abort()
    }
  }

  async function run(...args) {
    abortInFlight()
    lastArgs = args
    const current = ++seq
    controller = new AbortController()
    loading.value = true
    error.value = null
    try {
      const result = await taskFn(controller.signal, ...args)
      if (current !== seq || disposed) return undefined
      data.value = result
      return result
    } catch (err) {
      if (isAbortError(err)) return undefined
      if (current !== seq || disposed) return undefined
      error.value = err?.message || '请求失败'
      return undefined
    } finally {
      if (current === seq && !disposed) {
        loading.value = false
      }
    }
  }

  function retry() {
    if (!lastArgs) return undefined
    return run(...lastArgs)
  }

  function cancel() {
    if (!controller || controller.signal.aborted) return
    seq += 1 // 使在途任务失效，迟到的结果不写入
    controller.abort()
    loading.value = false
  }

  if (getCurrentInstance()) {
    onUnmounted(() => {
      disposed = true
      abortInFlight()
    })
  }

  return { loading, error, data, run, retry, cancel }
}
