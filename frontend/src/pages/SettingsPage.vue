<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

const loading = ref(false)
const saving = ref(false)

const llmApiKey = ref('')
const llmApiBase = ref('https://api.deepseek.com/v1')
const llmModel = ref('deepseek-chat')

// Track if key was loaded masked (user hasn't typed a new one)
const keyMasked = ref(true)

const fetchSettings = async () => {
  loading.value = true
  try {
    const res = await axios.get(`${API_BASE}/settings`)
    llmApiKey.value = res.data.llm_api_key || ''
    llmApiBase.value = res.data.llm_api_base || 'https://api.deepseek.com/v1'
    llmModel.value = res.data.llm_model || 'deepseek-chat'
    keyMasked.value = !!res.data.llm_api_key && res.data.llm_api_key.includes('*')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取设置失败')
  } finally {
    loading.value = false
  }
}

const saveSettings = async () => {
  saving.value = true
  try {
    const payload: Record<string, string> = {
      llm_api_base: llmApiBase.value,
      llm_model: llmModel.value,
    }
    // Only send API key if user has typed a new one (not masked)
    if (!keyMasked.value && llmApiKey.value) {
      payload.llm_api_key = llmApiKey.value
    }
    await axios.put(`${API_BASE}/settings`, payload)
    ElMessage.success('保存成功')
    fetchSettings()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

const onKeyInput = () => {
  keyMasked.value = false
}

onMounted(fetchSettings)
</script>

<template>
  <div class="settings-page" v-loading="loading">
    <div class="page-header">
      <h2>设置</h2>
    </div>

    <el-card class="settings-card">
      <template #header>
        <span class="card-title">LLM API 配置</span>
      </template>
      <p class="card-desc">配置用于面试复盘AI总结的大语言模型API。支持 OpenAI 兼容接口（DeepSeek、OpenAI、智谱、通义千问等）。</p>

      <el-form label-width="120px" style="max-width: 600px; margin-top: 20px">
        <el-form-item label="API Key">
          <el-input
            v-model="llmApiKey"
            type="password"
            show-password
            placeholder="输入你的 API Key"
            @input="onKeyInput"
          />
        </el-form-item>

        <el-form-item label="API Base URL">
          <el-input v-model="llmApiBase" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>

        <el-form-item label="模型名称">
          <el-input v-model="llmModel" placeholder="deepseek-chat" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveSettings">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.settings-page {
  height: 100%;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  margin: 0;
  font-size: 24px;
  color: #1e3a5f;
}

.settings-card {
  max-width: 800px;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
  color: #1e3a5f;
}

.card-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0;
}
</style>
