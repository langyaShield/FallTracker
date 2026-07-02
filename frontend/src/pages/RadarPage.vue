<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, VideoPlay, VideoPause, Edit, Delete, CaretRight } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { formatLocaleDateTime } from '@/lib/format'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'
import RadarEmailSettings from '@/components/radar/RadarEmailSettings.vue'

// ========== Types ==========
interface CrawlerConfig {
  id: number
  user_id: number
  name: string
  url: string
  css_selector: string  // DEPRECATED
  interval_hours: number
  target_description: string
  email_to: string
  is_active: boolean
  extra_headers: string | null
  last_error: string | null
  consecutive_failures: number
  last_run_at: string | null
  created_at: string
  updated_at: string
}

interface MatchedItem {
  company: string | null
  position: string | null
  salary: string | null
  location: string | null
  link: string | null
  tags: string[] | null
  match_reason: string | null
}

interface CrawlerResult {
  id: number
  config_id: number
  raw_text: string
  analysis_result: any
  target_found: boolean
  email_sent: boolean
  matched_items: MatchedItem[] | null
  created_at: string
}

interface CrawlerTemplate {
  id: string
  name: string
  description: string
  url: string
  suggested_target: string
  site_tips: string[]
}

// ========== Tab State ==========
const activeTab = ref('configs')

// ========== Templates ==========
const templates = ref<CrawlerTemplate[]>([])

async function fetchTemplates() {
  try {
    const res = await api.get('/radar/templates')
    templates.value = res.data || []
  } catch {
    // 非关键功能，静默失败
  }
}

// ========== Configs Tab ==========
const configs = ref<CrawlerConfig[]>([])
const configsLoading = ref(false)

// 创建向导
const wizardVisible = ref(false)
const wizardStep = ref(0)  // 0: 选模板/自定义, 1: 填写信息, 2: 完成
const selectedTemplate = ref<CrawlerTemplate | null>(null)
const isCustomMode = ref(false)
const configForm = ref({
  name: '',
  url: '',
  extra_headers: '',
  interval_hours: 24,
  target_description: '',
  email_to: '',
  is_active: true,
})
const configSaving = ref(false)

// 编辑对话框
const editDialogVisible = ref(false)
const editingConfig = ref<CrawlerConfig | null>(null)
const editForm = ref({
  name: '',
  url: '',
  extra_headers: '',
  interval_hours: 24,
  target_description: '',
  email_to: '',
  is_active: true,
})
const editSaving = ref(false)
const showAdvanced = ref(false)

async function fetchConfigs() {
  configsLoading.value = true
  try {
    const res = await api.get('/radar/configs')
    configs.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取爬虫配置失败'))
  } finally {
    configsLoading.value = false
  }
}

// ─── 创建向导 ───

function openWizard() {
  wizardStep.value = 0
  selectedTemplate.value = null
  isCustomMode.value = false
  configForm.value = {
    name: '', url: '', extra_headers: '',
    interval_hours: 24, target_description: '',
    email_to: '', is_active: true,
  }
  wizardVisible.value = true
}

function selectTemplate(tpl: CrawlerTemplate) {
  selectedTemplate.value = tpl
  isCustomMode.value = false
  // 自动填充模板信息
  configForm.value.name = tpl.name + '监控'
  configForm.value.url = tpl.url
  configForm.value.target_description = tpl.suggested_target || ''
  wizardStep.value = 1
}

function selectCustom() {
  selectedTemplate.value = null
  isCustomMode.value = true
  configForm.value = {
    name: '', url: '', extra_headers: '',
    interval_hours: 24, target_description: '',
    email_to: '', is_active: true,
  }
  wizardStep.value = 1
}

function goBackToStep0() {
  wizardStep.value = 0
}

async function saveNewConfig() {
  if (!configForm.value.name || !configForm.value.url) {
    ElMessage.warning('请填写名称和目标网址')
    return
  }
  configSaving.value = true
  try {
    await api.post('/radar/configs', configForm.value)
    wizardStep.value = 2
    await fetchConfigs()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '创建失败'))
  } finally {
    configSaving.value = false
  }
}

function closeWizardAndRun() {
  wizardVisible.value = false
  // 找到刚创建的配置并运行
  const created = configs.value.find(c => c.name === configForm.value.name)
  if (created) {
    runNow(created)
  }
}

// ─── 编辑 ───

function openEditDialog(config: CrawlerConfig) {
  editingConfig.value = config
  editForm.value = {
    name: config.name,
    url: config.url,
    extra_headers: config.extra_headers || '',
    interval_hours: config.interval_hours,
    target_description: config.target_description,
    email_to: config.email_to,
    is_active: config.is_active,
  }
  showAdvanced.value = false
  editDialogVisible.value = true
}

async function saveEdit() {
  if (!editForm.value.name || !editForm.value.url) {
    ElMessage.warning('请填写名称和目标网址')
    return
  }
  editSaving.value = true
  try {
    await api.put(`/radar/configs/${editingConfig.value!.id}`, editForm.value)
    ElMessage.success('配置已更新')
    editDialogVisible.value = false
    await fetchConfigs()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  } finally {
    editSaving.value = false
  }
}

// ─── 操作 ───

async function deleteConfig(config: CrawlerConfig) {
  try {
    await ElMessageBox.confirm(`确定删除「${config.name}」？运行记录也将被删除。`, '确认删除', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await api.delete(`/radar/configs/${config.id}`)
    ElMessage.success('已删除')
    await fetchConfigs()
  } catch { /* cancelled */ }
}

async function runNow(config: CrawlerConfig) {
  try {
    await api.post(`/radar/configs/${config.id}/run`)
    ElMessage.success('已开始运行，预计 10-30 秒后出结果')
    selectedConfigId.value = config.id
    activeTab.value = 'results'
    await fetchConfigs()
    setTimeout(() => onConfigSelect(), 5000)
    setTimeout(() => onConfigSelect(), 15000)
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '运行失败'))
  }
}

async function toggleActive(config: CrawlerConfig) {
  try {
    await api.put(`/radar/configs/${config.id}`, { is_active: !config.is_active })
    await fetchConfigs()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '操作失败'))
  }
}

function formatTime(t: string | null) {
  return t ? formatLocaleDateTime(t) : '从未运行'
}

const intervalLabel = (h: number) => {
  if (h < 24) return `每${h}小时`
  const d = h / 24
  return d === 1 ? '每天' : `每${d}天`
}

// ========== Results Tab ==========
const selectedConfigId = ref<number | null>(null)
const results = ref<CrawlerResult[]>([])
const resultsLoading = ref(false)
const resultDetailVisible = ref(false)
const selectedResult = ref<CrawlerResult | null>(null)

async function onConfigSelect() {
  if (!selectedConfigId.value) {
    results.value = []
    return
  }
  resultsLoading.value = true
  try {
    const res = await api.get(`/radar/configs/${selectedConfigId.value}/results?limit=50`)
    results.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取运行记录失败'))
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
const emailLoading = ref(false)

// ========== Lifecycle ==========
onMounted(() => {
  fetchConfigs()
  fetchTemplates()
})
</script>

<template>
  <div class="radar-page">
    <PageHeader title="爬虫雷达" />

    <el-tabs v-model="activeTab" class="radar-tabs">
      <!-- ========== Tab 1: 我的监控 ========== -->
      <el-tab-pane label="我的监控" name="configs">
        <!-- 快速创建入口 -->
        <div class="quick-create-section">
          <div class="section-title">
            <h3>快速创建</h3>
            <span class="section-desc">选择招聘网站模板，一键创建监控</span>
          </div>
          <div class="template-cards">
            <div
              v-for="tpl in templates"
              :key="tpl.id"
              class="template-card"
              @click="selectTemplate(tpl); wizardVisible = true"
            >
              <div class="tpl-name">{{ tpl.name }}</div>
              <div class="tpl-desc">{{ tpl.description }}</div>
              <div v-if="tpl.site_tips.length" class="tpl-notes">
                <span v-for="tip in tpl.site_tips" :key="tip" class="tpl-note">{{ tip }}</span>
              </div>
              <el-button type="primary" size="small" class="tpl-btn">
                <el-icon><CaretRight /></el-icon> 使用此模板
              </el-button>
            </div>
            <!-- 自定义创建卡片 -->
            <div class="template-card custom-card" @click="selectCustom(); wizardVisible = true">
              <div class="tpl-name">自定义网站</div>
              <div class="tpl-desc">手动填写任意网站的监控配置</div>
              <el-button size="small" class="tpl-btn">
                <el-icon><Plus /></el-icon> 自定义创建
              </el-button>
            </div>
          </div>
        </div>

        <!-- 已有配置列表 -->
        <div class="configs-section">
          <div class="section-title">
            <h3>我的监控</h3>
            <el-button type="primary" size="small" :icon="Plus" @click="openWizard">新建监控</el-button>
          </div>

          <div v-loading="configsLoading" class="config-list">
            <el-card v-for="config in configs" :key="config.id" class="config-card">
              <div class="config-header">
                <div class="config-info">
                  <span class="config-name">{{ config.name }}</span>
                  <el-tag :type="config.is_active ? 'success' : 'info'" size="small">
                    {{ config.is_active ? '监控中' : '已暂停' }}
                  </el-tag>
                </div>
                <div class="config-actions">
                  <el-button size="small" type="primary" :icon="VideoPlay" @click="runNow(config)">立即检查</el-button>
                  <el-button size="small" :icon="config.is_active ? VideoPause : VideoPlay" @click="toggleActive(config)">
                    {{ config.is_active ? '暂停' : '启用' }}
                  </el-button>
                  <el-button size="small" :icon="Edit" @click="openEditDialog(config)">编辑</el-button>
                  <el-button size="small" type="danger" :icon="Delete" @click="deleteConfig(config)">删除</el-button>
                </div>
              </div>
              <div class="config-detail">
                <div class="detail-row">
                  <span class="detail-label">目标网址</span>
                  <span class="detail-value url-value">{{ config.url }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">检查频率</span>
                  <span class="detail-value">{{ intervalLabel(config.interval_hours) }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">寻找目标</span>
                  <span class="detail-value desc-value">{{ config.target_description || '未设置' }}</span>
                </div>
                <div class="detail-row">
                  <span class="detail-label">上次检查</span>
                  <span class="detail-value time-value">{{ formatTime(config.last_run_at) }}</span>
                </div>
                <div v-if="config.last_error" class="detail-row error-row">
                  <span class="detail-label">最近错误</span>
                  <span class="detail-value error-value">{{ config.last_error }}</span>
                </div>
                <div v-if="config.consecutive_failures >= 3" class="detail-row warning-row">
                  <el-tag type="warning" size="small">连续失败 {{ config.consecutive_failures }} 次</el-tag>
                </div>
              </div>
            </el-card>
            <el-empty v-if="!configsLoading && configs.length === 0" description="暂无监控，点击上方模板快速创建" />
          </div>
        </div>

        <!-- 创建向导对话框 -->
        <el-dialog
          v-model="wizardVisible"
          :title="wizardStep === 0 ? '选择创建方式' : wizardStep === 1 ? '填写监控信息' : '创建成功'"
          width="600px"
          :close-on-click-modal="wizardStep !== 1"
        >
          <!-- Step 0: 选择模板（弹窗内备用） -->
          <template v-if="wizardStep === 0">
            <div class="wizard-templates">
              <div
                v-for="tpl in templates"
                :key="tpl.id"
                class="wizard-tpl-item"
                @click="selectTemplate(tpl)"
              >
                <span class="wizard-tpl-name">{{ tpl.name }}</span>
                <span class="wizard-tpl-desc">{{ tpl.description }}</span>
              </div>
              <div class="wizard-tpl-item custom" @click="selectCustom()">
                <span class="wizard-tpl-name">自定义网站</span>
                <span class="wizard-tpl-desc">手动填写任意网站</span>
              </div>
            </div>
          </template>

          <!-- Step 1: 填写信息 -->
          <template v-if="wizardStep === 1">
            <div v-if="selectedTemplate" class="template-hint">
              <el-tag type="info" size="small">基于模板: {{ selectedTemplate.name }}</el-tag>
              <el-button type="primary" link size="small" @click="goBackToStep0">重新选择</el-button>
            </div>

            <el-form :model="configForm" label-width="100px" class="wizard-form">
              <el-form-item label="监控名称" required>
                <el-input v-model="configForm.name" placeholder="如：BOSS直聘-前端开发" />
              </el-form-item>
              <el-form-item label="目标网址" required>
                <el-input v-model="configForm.url" placeholder="https://www.zhipin.com/web/geek/job?query=前端" />
                <div class="form-tip">要监控的招聘网站页面地址，可直接从浏览器复制</div>
              </el-form-item>
              <el-form-item label="寻找目标">
                <el-input
                  v-model="configForm.target_description"
                  type="textarea"
                  :rows="3"
                  placeholder="用自然语言描述你想监控的岗位，例如：&#10;- 前端开发实习岗位，薪资8k以上&#10;- Java后端开发，本科及以上学历&#10;- 字节跳动或腾讯的数据分析岗位"
                />
                <div class="form-tip">AI 会自动分析页面内容，提取匹配的职位信息</div>
              </el-form-item>
              <el-form-item label="检查频率">
                <el-select v-model="configForm.interval_hours" style="width: 200px">
                  <el-option :value="1" label="每1小时" />
                  <el-option :value="6" label="每6小时" />
                  <el-option :value="12" label="每12小时" />
                  <el-option :value="24" label="每天一次" />
                  <el-option :value="48" label="每两天一次" />
                  <el-option :value="168" label="每周一次" />
                </el-select>
              </el-form-item>
              <el-form-item label="通知邮箱">
                <el-input v-model="configForm.email_to" placeholder="可选，匹配到目标时发邮件通知你" />
              </el-form-item>

              <!-- 高级选项（折叠） -->
              <el-collapse v-model="showAdvanced" class="advanced-collapse">
                <el-collapse-item title="高级选项（一般无需修改）" name="advanced">
                  <el-form-item label="自定义请求头">
                    <el-input
                      v-model="configForm.extra_headers"
                      type="textarea"
                      :rows="3"
                      placeholder='JSON格式，例如：&#10;{"Cookie": "your_cookie_value", "Referer": "https://example.com"}'
                    />
                    <div class="form-tip">部分网站需要Cookie才能访问，可从浏览器开发者工具复制</div>
                  </el-form-item>
                  <el-form-item label="立即启用">
                    <el-switch v-model="configForm.is_active" />
                  </el-form-item>
                </el-collapse-item>
              </el-collapse>
            </el-form>
          </template>

          <!-- Step 2: 完成 -->
          <template v-if="wizardStep === 2">
            <div class="wizard-success">
              <div class="success-icon">&#10003;</div>
              <h3>监控创建成功！</h3>
              <p>系统将按设定频率自动检查页面，匹配到目标时通知你。</p>
              <el-button type="primary" @click="closeWizardAndRun">立即检查一次</el-button>
              <el-button @click="wizardVisible = false">稍后再说</el-button>
            </div>
          </template>

          <template #footer v-if="wizardStep === 1">
            <el-button @click="wizardStep = 0">上一步</el-button>
            <el-button type="primary" :loading="configSaving" @click="saveNewConfig">创建监控</el-button>
          </template>
        </el-dialog>

        <!-- 编辑对话框 -->
        <el-dialog v-model="editDialogVisible" title="编辑监控" width="600px">
          <el-form :model="editForm" label-width="100px">
            <el-form-item label="监控名称" required>
              <el-input v-model="editForm.name" />
            </el-form-item>
            <el-form-item label="目标网址" required>
              <el-input v-model="editForm.url" />
            </el-form-item>
            <el-form-item label="寻找目标">
              <el-input v-model="editForm.target_description" type="textarea" :rows="3" />
            </el-form-item>
            <el-form-item label="检查频率">
              <el-select v-model="editForm.interval_hours" style="width: 200px">
                <el-option :value="1" label="每1小时" />
                <el-option :value="6" label="每6小时" />
                <el-option :value="12" label="每12小时" />
                <el-option :value="24" label="每天一次" />
                <el-option :value="48" label="每两天一次" />
                <el-option :value="168" label="每周一次" />
              </el-select>
            </el-form-item>
            <el-form-item label="通知邮箱">
              <el-input v-model="editForm.email_to" />
            </el-form-item>
            <el-collapse class="advanced-collapse">
              <el-collapse-item title="高级选项" name="advanced">
                <el-form-item label="自定义请求头">
                  <el-input
                    v-model="editForm.extra_headers"
                    type="textarea"
                    :rows="3"
                    placeholder='JSON格式，例如：&#10;{"Cookie": "your_cookie_value"}'
                  />
                </el-form-item>
                <el-form-item label="启用监控">
                  <el-switch v-model="editForm.is_active" />
                </el-form-item>
              </el-collapse-item>
            </el-collapse>
          </el-form>
          <template #footer>
            <el-button @click="editDialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ========== Tab 2: 运行记录 ========== -->
      <el-tab-pane label="运行记录" name="results">
        <div class="section-header">
          <el-select
            v-model="selectedConfigId"
            placeholder="选择监控项"
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

        <el-table :data="results" v-loading="resultsLoading" stripe style="width: 100%">
          <el-table-column label="检查时间" width="160">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
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
          <el-table-column label="邮件" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.email_sent" type="warning" size="small">已发</el-tag>
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
        <el-dialog v-model="resultDetailVisible" title="运行详情" width="700px">
          <template v-if="selectedResult">
            <div class="detail-section">
              <h4>检查时间</h4>
              <p>{{ formatTime(selectedResult.created_at) }}</p>
            </div>
            <!-- AI 提取结果 -->
            <div v-if="selectedResult.matched_items && selectedResult.matched_items.length > 0" class="detail-section">
              <h4>AI 提取结果 <el-tag size="small" type="success" style="margin-left: 8px">{{ selectedResult.matched_items.length }} 个匹配职位</el-tag></h4>
              <el-table :data="selectedResult.matched_items" stripe size="small" style="width: 100%">
                <el-table-column prop="company" label="公司" min-width="120">
                  <template #default="{ row }">{{ row.company || '-' }}</template>
                </el-table-column>
                <el-table-column prop="position" label="岗位" min-width="120">
                  <template #default="{ row }">{{ row.position || '-' }}</template>
                </el-table-column>
                <el-table-column prop="salary" label="薪资" width="100">
                  <template #default="{ row }">{{ row.salary || '-' }}</template>
                </el-table-column>
                <el-table-column prop="location" label="地点" width="80">
                  <template #default="{ row }">{{ row.location || '-' }}</template>
                </el-table-column>
                <el-table-column label="链接" width="60">
                  <template #default="{ row }">
                    <a v-if="row.link" :href="row.link" target="_blank" rel="noopener noreferrer" style="color: #409eff">查看</a>
                    <span v-else>-</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>
            <div class="detail-section">
              <h4>AI 分析结果</h4>
              <el-tag :type="selectedResult.target_found ? 'success' : 'info'">
                {{ selectedResult.target_found ? '目标匹配' : '未匹配' }}
              </el-tag>
              <pre class="analysis-json">{{ JSON.stringify(selectedResult.analysis_result, null, 2) }}</pre>
            </div>
            <div class="detail-section">
              <h4>抓取内容 <el-tag size="small" style="margin-left: 8px">{{ selectedResult.raw_text.length }} 字符</el-tag></h4>
              <pre class="raw-text">{{ selectedResult.raw_text }}</pre>
            </div>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ========== Tab 3: 通知设置 ========== -->
      <el-tab-pane label="通知设置" name="email">
        <RadarEmailSettings v-model:loading="emailLoading" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.radar-page { padding: 0; }

.radar-tabs {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
}

/* ─── 快速创建区域 ─── */
.quick-create-section {
  margin-bottom: 28px;
  padding: 20px;
  background: linear-gradient(135deg, #f0f7ff 0%, #f5f0ff 100%);
  border-radius: 10px;
}

.section-title {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}

.section-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
}

.section-desc {
  font-size: 13px;
  color: #64748b;
}

.template-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 14px;
}

.template-card {
  background: #fff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.template-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 8px rgba(64, 158, 255, 0.15);
  transform: translateY(-1px);
}

.custom-card {
  border-style: dashed;
  background: #fafbfc;
}

.tpl-name {
  font-weight: 600;
  font-size: 15px;
  color: #1e293b;
}

.tpl-desc {
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
  flex: 1;
}

.tpl-notes {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.tpl-note {
  font-size: 11px;
  color: #d97706;
  background: #fffbeb;
  padding: 2px 6px;
  border-radius: 3px;
}

.tpl-btn {
  align-self: flex-start;
  margin-top: 4px;
}

/* ─── 配置列表 ─── */
.configs-section .section-title {
  justify-content: space-between;
}

.config-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-card {
  border-radius: 8px;
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.config-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.config-name {
  font-weight: 600;
  font-size: 15px;
  color: #1e293b;
}

.config-actions {
  display: flex;
  gap: 6px;
}

.config-detail {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 24px;
}

.detail-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
  line-height: 1.5;
}

.detail-label {
  color: #94a3b8;
  white-space: nowrap;
  min-width: 64px;
}

.detail-value {
  color: #334155;
  word-break: break-all;
}

.url-value {
  font-size: 12px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.desc-value {
  color: #475569;
}

.time-value {
  color: #94a3b8;
  font-size: 12px;
}

.error-row .error-value {
  color: #ef4444;
  font-size: 12px;
  word-break: break-all;
}

.warning-row {
  grid-column: 1 / -1;
}

/* ─── 向导 ─── */
.template-hint {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #f0f7ff;
  border-radius: 6px;
}

.wizard-form {
  max-height: 55vh;
  overflow-y: auto;
  padding-right: 8px;
}

.advanced-collapse {
  margin-top: 12px;
  border: none;
}

.advanced-collapse :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #94a3b8;
  border-bottom: none;
  height: 36px;
  line-height: 36px;
}

.advanced-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

.wizard-templates {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.wizard-tpl-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}

.wizard-tpl-item:hover {
  border-color: #409eff;
  background: #f0f7ff;
}

.wizard-tpl-item.custom {
  border-style: dashed;
}

.wizard-tpl-name {
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
}

.wizard-tpl-desc {
  font-size: 13px;
  color: #64748b;
}

.wizard-success {
  text-align: center;
  padding: 24px 0;
}

.success-icon {
  font-size: 48px;
  color: #67c23a;
  margin-bottom: 12px;
}

.wizard-success h3 {
  font-size: 18px;
  color: #1e293b;
  margin: 0 0 8px 0;
}

.wizard-success p {
  color: #64748b;
  margin: 0 0 20px 0;
}

/* ─── 通用 ─── */
.form-tip {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
  line-height: 1.4;
}

.section-header {
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
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

.no-email { color: #94a3b8; }

.detail-section { margin-bottom: 20px; }
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

@media (max-width: 768px) {
  .config-detail {
    grid-template-columns: 1fr;
  }

  .config-actions {
    flex-wrap: wrap;
    gap: 6px;
  }

  .config-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .template-cards {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
}
</style>
