<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api'

// ========== Types ==========
interface CrawlerConfig {
  id: number
  user_id: number
  name: string
  url: string
  css_selector: string
  interval_hours: number
  target_description: string
  email_to: string
  is_active: boolean
  last_run_at: string | null
  created_at: string
  updated_at: string
}

interface CrawlerResult {
  id: number
  config_id: number
  raw_text: string
  analysis_result: any
  target_found: boolean
  email_sent: boolean
  created_at: string
}

interface EmailSettings {
  smtp_server: string
  smtp_port: number
  smtp_username: string
  smtp_password: string
  email_from: string
}

// ========== Tab State ==========
const activeTab = ref('configs')

// ========== Configs Tab ==========
const configs = ref<CrawlerConfig[]>([])
const configsLoading = ref(false)
const configDialogVisible = ref(false)
const editingConfig = ref<CrawlerConfig | null>(null)
const configForm = ref({
  name: '',
  url: '',
  css_selector: '',
  interval_hours: 24,
  target_description: '',
  email_to: '',
  is_active: true,
})
const configSaving = ref(false)

async function fetchConfigs() {
  configsLoading.value = true
  try {
    const res = await axios.get(`${API_BASE}/radar/configs`)
    configs.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取爬虫配置失败')
  } finally {
    configsLoading.value = false
  }
}

function openAddDialog() {
  editingConfig.value = null
  configForm.value = {
    name: '',
    url: '',
    css_selector: '',
    interval_hours: 24,
    target_description: '',
    email_to: '',
    is_active: true,
  }
  configDialogVisible.value = true
}

function openEditDialog(config: CrawlerConfig) {
  editingConfig.value = config
  configForm.value = {
    name: config.name,
    url: config.url,
    css_selector: config.css_selector,
    interval_hours: config.interval_hours,
    target_description: config.target_description,
    email_to: config.email_to,
    is_active: config.is_active,
  }
  configDialogVisible.value = true
}

async function saveConfig() {
  configSaving.value = true
  try {
    if (editingConfig.value) {
      await axios.put(`${API_BASE}/radar/configs/${editingConfig.value.id}`, configForm.value)
      ElMessage.success('配置已更新')
    } else {
      await axios.post(`${API_BASE}/radar/configs`, configForm.value)
      ElMessage.success('配置已创建')
    }
    configDialogVisible.value = false
    await fetchConfigs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    configSaving.value = false
  }
}

async function deleteConfig(config: CrawlerConfig) {
  try {
    await ElMessageBox.confirm(`确定删除爬虫「${config.name}」？相关的运行记录也将被删除。`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await axios.delete(`${API_BASE}/radar/configs/${config.id}`)
    ElMessage.success('已删除')
    await fetchConfigs()
  } catch {
    // cancelled
  }
}

async function runNow(config: CrawlerConfig) {
  try {
    await axios.post(`${API_BASE}/radar/configs/${config.id}/run`)
    ElMessage.success('爬虫已开始运行')
    await fetchConfigs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '运行失败')
  }
}

async function toggleActive(config: CrawlerConfig) {
  try {
    await axios.put(`${API_BASE}/radar/configs/${config.id}`, { is_active: !config.is_active })
    await fetchConfigs()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

function formatTime(t: string | null) {
  if (!t) return '从未运行'
  const d = new Date(t)
  return d.toLocaleString('zh-CN')
}

// ========== Results Tab ==========
const selectedConfigId = ref<number | null>(null)
const results = ref<CrawlerResult[]>([])
const resultsLoading = ref(false)
const resultDetailVisible = ref(false)
const selectedResult = ref<CrawlerResult | null>(null)
const resultsConfigName = ref('')

async function onConfigSelect() {
  if (!selectedConfigId.value) {
    results.value = []
    return
  }
  const cfg = configs.value.find(c => c.id === selectedConfigId.value)
  resultsConfigName.value = cfg?.name || ''
  resultsLoading.value = true
  try {
    const res = await axios.get(`${API_BASE}/radar/configs/${selectedConfigId.value}/results?limit=50`)
    results.value = res.data
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取运行记录失败')
  } finally {
    resultsLoading.value = false
  }
}

function showResultDetail(result: CrawlerResult) {
  selectedResult.value = result
  resultDetailVisible.value = true
}

function analysisSummary(analysis: any): string {
  if (!analysis) return '无分析结果'
  if (analysis.error) return `错误: ${analysis.error}`
  return analysis.summary || analysis.reasoning || '无摘要'
}

// ========== Email Settings Tab ==========
const emailSettings = ref<EmailSettings>({
  smtp_server: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  email_from: '',
})
const emailLoading = ref(false)
const emailSaving = ref(false)
const passwordMasked = ref(true)

async function fetchEmailSettings() {
  emailLoading.value = true
  try {
    const res = await axios.get(`${API_BASE}/settings/email`)
    emailSettings.value = res.data
    passwordMasked.value = !!res.data.smtp_password && res.data.smtp_password.includes('*')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '获取邮箱配置失败')
  } finally {
    emailLoading.value = false
  }
}

function onPasswordInput() {
  passwordMasked.value = false
}

async function saveEmailSettings() {
  emailSaving.value = true
  try {
    const payload: Record<string, any> = {
      smtp_server: emailSettings.value.smtp_server,
      smtp_port: emailSettings.value.smtp_port || 587,
      smtp_username: emailSettings.value.smtp_username,
      email_from: emailSettings.value.email_from,
    }
    if (!passwordMasked.value && emailSettings.value.smtp_password) {
      payload.smtp_password = emailSettings.value.smtp_password
    }
    await axios.put(`${API_BASE}/settings/email`, payload)
    ElMessage.success('邮箱配置已保存')
    await fetchEmailSettings()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    emailSaving.value = false
  }
}

// ========== Lifecycle ==========
onMounted(() => {
  fetchConfigs()
  fetchEmailSettings()
})
</script>

<template>
  <div class="radar-page">
    <div class="page-header">
      <h2>爬虫雷达</h2>
    </div>

    <el-tabs v-model="activeTab" class="radar-tabs">
      <!-- ========== Tab 1: 爬虫配置 ========== -->
      <el-tab-pane label="爬虫配置" name="configs">
        <div class="section-header">
          <el-button type="primary" @click="openAddDialog">+ 添加爬虫</el-button>
        </div>

        <el-table
          :data="configs"
          v-loading="configsLoading"
          style="width: 100%"
          stripe
        >
          <el-table-column prop="name" label="名称" min-width="120" />
          <el-table-column prop="url" label="目标URL" min-width="220" show-overflow-tooltip />
          <el-table-column label="运行间隔" width="100">
            <template #default="{ row }">
              {{ row.interval_hours }}小时
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
                {{ row.is_active ? '活跃' : '暂停' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="上次运行" width="160">
            <template #default="{ row }">
              <span class="time-text">{{ formatTime(row.last_run_at) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="runNow(row)">运行</el-button>
              <el-button size="small" @click="toggleActive(row)">
                {{ row.is_active ? '暂停' : '启用' }}
              </el-button>
              <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteConfig(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="!configsLoading && configs.length === 0" description="暂无爬虫配置，点击上方添加" />

        <!-- Add/Edit Dialog -->
        <el-dialog
          v-model="configDialogVisible"
          :title="editingConfig ? '编辑爬虫' : '添加爬虫'"
          width="600px"
        >
          <el-form :model="configForm" label-width="120px">
            <el-form-item label="爬虫名称" required>
              <el-input v-model="configForm.name" placeholder="例如：XX公司招聘监控" />
            </el-form-item>
            <el-form-item label="目标URL" required>
              <el-input v-model="configForm.url" placeholder="https://example.com/jobs" />
            </el-form-item>
            <el-form-item label="CSS选择器">
              <el-input v-model="configForm.css_selector" placeholder="可选，如 .job-list .item（留空则抓取整页）" />
              <span class="form-tip">指定要抓取的HTML元素CSS选择器，留空则抓取整页文本</span>
            </el-form-item>
            <el-form-item label="运行间隔" required>
              <el-input-number v-model="configForm.interval_hours" :min="1" :max="720" />
              <span class="form-tip">小时</span>
            </el-form-item>
            <el-form-item label="爬虫目标">
              <el-input
                v-model="configForm.target_description"
                type="textarea"
                :rows="3"
                placeholder="描述你要寻找的目标，例如：招聘高级前端工程师，月薪30K以上"
              />
              <span class="form-tip">抓取结果将与目标一起交由LLM分析是否匹配</span>
            </el-form-item>
            <el-form-item label="通知邮箱">
              <el-input v-model="configForm.email_to" placeholder="可选，匹配到目标时发送邮件到此地址" />
            </el-form-item>
            <el-form-item label="启用">
              <el-switch v-model="configForm.is_active" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="configDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="configSaving" @click="saveConfig">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ========== Tab 2: 运行记录 ========== -->
      <el-tab-pane label="运行记录" name="results">
        <div class="section-header">
          <el-select
            v-model="selectedConfigId"
            placeholder="选择爬虫配置"
            style="width: 320px"
            @change="onConfigSelect"
          >
            <el-option
              v-for="c in configs"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </div>

        <el-table
          :data="results"
          v-loading="resultsLoading"
          style="width: 100%"
          stripe
        >
          <el-table-column label="运行时间" width="160">
            <template #default="{ row }">
              {{ formatTime(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="分析结果" min-width="300">
            <template #default="{ row }">
              <div class="result-summary">
                <el-tag v-if="row.target_found" type="success" size="small" effect="dark">匹配</el-tag>
                <el-tag v-else type="info" size="small" effect="plain">未匹配</el-tag>
                <span class="summary-text">{{ analysisSummary(row.analysis_result) }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="邮件通知" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.email_sent" type="warning" size="small">已发送</el-tag>
              <span v-else class="no-email">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ row }">
              <el-button size="small" @click="showResultDetail(row)">详情</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="selectedConfigId && !resultsLoading && results.length === 0" description="暂无运行记录" />

        <!-- Result Detail Dialog -->
        <el-dialog
          v-model="resultDetailVisible"
          title="运行详情"
          width="700px"
        >
          <template v-if="selectedResult">
            <div class="detail-section">
              <h4>抓取时间</h4>
              <p>{{ formatTime(selectedResult.created_at) }}</p>
            </div>
            <div class="detail-section">
              <h4>LLM 分析结果</h4>
              <el-tag :type="selectedResult.target_found ? 'success' : 'info'">
                {{ selectedResult.target_found ? '目标匹配' : '未匹配' }}
              </el-tag>
              <pre class="analysis-json">{{ JSON.stringify(selectedResult.analysis_result, null, 2) }}</pre>
            </div>
            <div class="detail-section">
              <h4>
                抓取内容
                <el-tag size="small" style="margin-left: 8px">{{ selectedResult.raw_text.length }} 字符</el-tag>
              </h4>
              <pre class="raw-text">{{ selectedResult.raw_text }}</pre>
            </div>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ========== Tab 3: 邮箱配置 ========== -->
      <el-tab-pane label="邮箱配置" name="email">
        <el-card v-loading="emailLoading" class="settings-card">
          <template #header>
            <span class="card-title">SMTP 邮箱配置</span>
          </template>
          <p class="card-desc">配置SMTP邮箱信息后，当爬虫匹配到目标时可以自动发送邮件通知。</p>

          <el-form :model="emailSettings" label-width="140px" style="max-width: 520px; margin-top: 20px">
            <el-form-item label="SMTP 服务器">
              <el-input v-model="emailSettings.smtp_server" placeholder="smtp.qq.com" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="emailSettings.smtp_port" :min="1" :max="65535" />
              <span class="form-tip">通常 587（TLS）或 465（SSL）</span>
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="emailSettings.smtp_username" placeholder="your@email.com" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input
                v-model="emailSettings.smtp_password"
                type="password"
                show-password
                placeholder="输入SMTP密码/授权码"
                @input="onPasswordInput"
              />
              <span class="form-tip">部分邮箱需使用授权码而非登录密码</span>
            </el-form-item>
            <el-form-item label="发件人邮箱">
              <el-input v-model="emailSettings.email_from" placeholder="your@email.com" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="emailSaving" @click="saveEmailSettings">
                保存配置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.radar-page {
  padding: 0;
}

.page-header h2 {
  font-size: 22px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 20px 0;
}

.radar-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
}

.section-header {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.time-text {
  color: #94a3b8;
  font-size: 13px;
}

.result-summary {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.summary-text {
  font-size: 13px;
  color: #475569;
  line-height: 1.4;
}

.no-email {
  color: #94a3b8;
}

.form-tip {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}

.detail-section {
  margin-bottom: 20px;
}

.detail-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  margin: 0 0 8px 0;
}

.analysis-json {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  margin-top: 8px;
}

.raw-text {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 12px;
  font-size: 13px;
  line-height: 1.5;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.settings-card {
  max-width: 680px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.card-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0;
}
</style>
