import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import eslintConfigPrettier from 'eslint-config-prettier'
import globals from 'globals'

export default [
  // JS 基础规则
  js.configs.recommended,

  // Vue 3 推荐规则（flat config）
  ...pluginVue.configs['flat/recommended'],

  // 所有 JS/Vue 文件的公共配置
  {
    files: ['**/*.{js,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
      },
    },
    rules: {
      // 单用户小工具，不强制多词组件名（App/LoginView 等命名自由）
      'vue/multi-word-component-names': 'off',
      // 未使用变量视为错误，但允许以 _ 开头的占位参数
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },

  // 关闭所有与 Prettier 冲突的格式规则（模板缩进/换行/属性换行等），
  // 格式化全权交给 Prettier，ESLint 只管代码质量
  eslintConfigPrettier,

  // 忽略构建产物与依赖
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
]
