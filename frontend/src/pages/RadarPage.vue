<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, VideoPlay, VideoPause, Edit, Delete, CaretRight, Loading } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { formatLocaleDateTime } from '@/lib/format'
import { STATUS_COLUMNS } from '@/lib/constants'
import { useUndoDelete } from '@/composables/useUndoDelete'
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

// ========== Test Panel Types ==========
interface TestFetchResult {
  success: boolean
  elapsed_ms: number
  status_code: number
  content_length: number
  content: string
  error: string
  engine: string
  engine_used: string
}

interface TestAnalyzeResult {
  success: boolean
  elapsed_ms: number
  analysis: Record<string, any>
  error: string
}

interface TestFullResult {
  success: boolean
  total_elapsed_ms: number
  fetch: TestFetchResult
  analyze: TestAnalyzeResult
}
// ========== Tab State ==========
const activeTab = ref('configs')

// ========== Configs Tab ==========
const configs = ref<CrawlerConfig[]>([])
const configsLoading = ref(false)

// 删除撤销
const { pendingIds: deletingConfigIds, requestDelete: requestDeleteConfig } = useUndoDelete<CrawlerConfig>({
  getId: (c) => c.id,
  getName: (c) => c.name,
  deleteFn: async (c) => {
    await api.delete(`/radar/configs/${c.id}`)
  },
  onSuccess: () => fetchConfigs(),
})

const displayedConfigs = computed(() => configs.value.filter((c) => !deletingConfigIds.value.has(c.id)))

// 创建向导
const wizardVisible = ref(false)
const wizardStep = ref(1)  // 1: 填写信息, 2: 完成
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
  wizardStep.value = 1
  configForm.value = {
    name: '', url: '', extra_headers: '',
    interval_hours: 24, target_description: '',
    email_to: '', is_active: true,
  }
  wizardVisible.value = true
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

async function saveEdit(runAfter = false) {
  if (!editForm.value.name || !editForm.value.url) {
    ElMessage.warning('请填写名称和目标网址')
    return
  }
  editSaving.value = true
  try {
    await api.put(`/radar/configs/${editingConfig.value!.id}`, editForm.value)
    ElMessage.success(runAfter ? '配置已更新，正在运行测试检查' : '配置已更新')
    editDialogVisible.value = false
    await fetchConfigs()
    if (runAfter && editingConfig.value) {
      runNow(editingConfig.value)
    }
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  } finally {
    editSaving.value = false
  }
}

// ─── 操作 ───

function deleteConfig(config: CrawlerConfig) {
  requestDeleteConfig(config)
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

// ========== Quick Delivery ==========
interface QuickDeliveryForm {
  company: string
  position: string
  city: string
  link: string
  jd_text: string
  status: string
  tags: string[]
}

const quickDeliveryVisible = ref(false)
const quickDeliveryLoading = ref(false)
const quickDeliveryForm = ref<QuickDeliveryForm>({
  company: '',
  position: '',
  city: '',
  link: '',
  jd_text: '',
  status: 'pending',
  tags: [],
})

function openQuickDelivery(item: MatchedItem) {
  quickDeliveryForm.value = {
    company: item.company || '',
    position: item.position || '',
    city: item.location || '',
    link: item.link || '',
    jd_text: item.match_reason ? `匹配原因：${item.match_reason}` : '',
    status: 'pending',
    tags: item.tags ? [...item.tags] : [],
  }
  quickDeliveryVisible.value = true
}

async function saveQuickDelivery() {
  if (!quickDeliveryForm.value.company || !quickDeliveryForm.value.position) {
    ElMessage.warning('请填写公司和岗位')
    return
  }
  quickDeliveryLoading.value = true
  try {
    const city = quickDeliveryForm.value.city.trim()
    const note = quickDeliveryForm.value.jd_text.trim()
    const jdText = city ? `城市：${city}\n\n${note}` : note
    await api.post('/deliveries', {
      company: quickDeliveryForm.value.company,
      position: quickDeliveryForm.value.position,
      status: quickDeliveryForm.value.status,
      link: quickDeliveryForm.value.link || undefined,
      jd_text: jdText || undefined,
      tags: quickDeliveryForm.value.tags,
    })
    ElMessage.success('已创建投递')
    quickDeliveryVisible.value = false
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '创建投递失败'))
  } finally {
    quickDeliveryLoading.value = false
  }
}

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

// ========== Test Panel State ==========
// Test 1: Fetch
const testFetchUrl = ref('')
const testFetchExtraHeaders = ref('')
const testFetchLoading = ref(false)
const testFetchResult = ref<TestFetchResult | null>(null)

// Test 2: Analyze
const testAnalyzeTarget = ref('')
const testAnalyzeContent = ref('')
const testAnalyzeLoading = ref(false)
const testAnalyzeResult = ref<TestAnalyzeResult | null>(null)

// Test 3: Full
const testFullUrl = ref('')
const testFullTarget = ref('')
const testFullExtraHeaders = ref('')
const testFullLoading = ref(false)
const testFullResult = ref<TestFullResult | null>(null)

// ========== Test Panel Methods ==========

// Test 1: Page Fetch
async function runTestFetch() {
  if (!testFetchUrl.value) {
    ElMessage.warning('请输入目标网址')
    return
  }
  testFetchLoading.value = true
  testFetchResult.value = null
  try {
    const payload: any = { url: testFetchUrl.value }
    if (testFetchExtraHeaders.value.trim()) {
      payload.extra_headers = testFetchExtraHeaders.value
    }
    const res = await api.post('/radar/test/fetch', payload)
    testFetchResult.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '抓取测试失败'))
  } finally {
    testFetchLoading.value = false
  }
}

// 将抓取结果填入分析测试的 content 字段
function useFetchResultForAnalyze() {
  if (testFetchResult.value?.content) {
    testAnalyzeContent.value = testFetchResult.value.content
    ElMessage.success('已填入抓取内容，可在下方"LLM分析测试"中测试')
  }
}

// Test 2: LLM Analyze
async function runTestAnalyze() {
  if (!testAnalyzeTarget.value) {
    ElMessage.warning('请输入目标描述')
    return
  }
  if (!testAnalyzeContent.value) {
    ElMessage.warning('请输入页面内容')
    return
  }
  testAnalyzeLoading.value = true
  testAnalyzeResult.value = null
  try {
    const res = await api.post('/radar/test/analyze', {
      target_description: testAnalyzeTarget.value,
      content: testAnalyzeContent.value,
    })
    testAnalyzeResult.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, 'LLM分析测试失败'))
  } finally {
    testAnalyzeLoading.value = false
  }
}

// Test 3: Full Pipeline
async function runTestFull() {
  if (!testFullUrl.value) {
    ElMessage.warning('请输入目标网址')
    return
  }
  if (!testFullTarget.value) {
    ElMessage.warning('请输入目标描述')
    return
  }
  testFullLoading.value = true
  testFullResult.value = null
  try {
    const payload: any = {
      url: testFullUrl.value,
      target_description: testFullTarget.value,
    }
    if (testFullExtraHeaders.value.trim()) {
      payload.extra_headers = testFullExtraHeaders.value
    }
    const res = await api.post('/radar/test/full', payload)
    testFullResult.value = res.data
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '全流程测试失败'))
  } finally {
    testFullLoading.value = false
  }
}

// ========== Lifecycle ==========
onMounted(() => {
  fetchConfigs()
})
</script>

<template>
  <div class="radar-page">
    <PageHeader title="爬虫雷达" />

    <el-tabs v-model="activeTab" class="radar-tabs">
      <!-- ========== Tab 1: 我的监控 ========== -->
      <el-tab-pane label="我的监控" name="configs">
        <!-- 已有配置列表 -->
        <div class="configs-section">
          <div class="section-title">
            <h3>我的监控</h3>
            <el-button type="primary" size="small" :icon="Plus" @click="openWizard">新建监控</el-button>
          </div>

          <div v-loading="configsLoading" class="config-list">
            <el-card v-for="config in displayedConfigs" :key="config.id" class="config-card">
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
            <el-empty v-if="!configsLoading && displayedConfigs.length === 0" description="暂无监控，点击上方按钮快速创建" />
          </div>
        </div>

        <!-- 创建向导对话框 -->
        <el-dialog
          v-model="wizardVisible"
          :title="wizardStep === 1 ? '填写监控信息' : '创建成功'"
          width="600px"
          :close-on-click-modal="wizardStep !== 1"
        >
          <!-- Step 1: 填写信息 -->
          <template v-if="wizardStep === 1">
            <el-form :model="configForm" label-width="100px" class="wizard-form">
              <el-form-item label="监控名称" required>
                <el-input v-model="configForm.name" placeholder="如：BOSS直聘-前端开发" />
              </el-form-item>
              <el-form-item label="目标网址" required>
                <el-input v-model="configForm.url" placeholder="https://www.zhipin.com/web/geek/job?query=前端" />
                <div class="form-tip">要监控的网页地址，可直接从浏览器复制</div>
              </el-form-item>
              <el-form-item label="寻找目标">
                <el-input
                  v-model="configForm.target_description"
                  type="textarea"
                  :rows="3"
                  placeholder="用自然语言描述你想监控的内容（留空则只抓取页面更新通知），例如：&#10;- 前端开发实习岗位，薪资8k以上&#10;- 字节跳动或腾讯的数据分析岗位&#10;- 某商品是否上架 / 某页面是否有公告更新"
                />
                <div class="form-tip">AI 会自动分析页面内容，提取匹配的信息条目；留空时仅做页面更新通知</div>
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
            <el-button @click="wizardVisible = false">取消</el-button>
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
              <el-input v-model="editForm.target_description" type="textarea" :rows="3" placeholder="用自然语言描述监控目标，留空则仅抓取页面更新通知" />
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
            <el-button type="primary" :loading="editSaving" @click="saveEdit(false)">保存</el-button>
            <el-button :loading="editSaving" @click="saveEdit(true)">保存并运行</el-button>
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
              <h4>AI 提取结果 <el-tag size="small" type="success" style="margin-left: 8px">{{ selectedResult.matched_items.length }} 条匹配内容</el-tag></h4>
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
                <el-table-column label="操作" width="100">
                  <template #default="{ row }">
                    <el-button v-if="row.company || row.position" type="primary" size="small" :icon="Plus" @click="openQuickDelivery(row)">快速投递</el-button>
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

        <!-- Quick Delivery Dialog -->
        <el-dialog v-model="quickDeliveryVisible" title="快速投递" width="520px">
          <el-form label-width="80px">
            <el-form-item label="公司" required>
              <el-input v-model="quickDeliveryForm.company" placeholder="公司名称" />
            </el-form-item>
            <el-form-item label="岗位" required>
              <el-input v-model="quickDeliveryForm.position" placeholder="岗位名称" />
            </el-form-item>
            <el-form-item label="城市">
              <el-input v-model="quickDeliveryForm.city" placeholder="工作城市" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="quickDeliveryForm.status" placeholder="选择状态" style="width: 100%">
                <el-option v-for="s in STATUS_COLUMNS" :key="s.key" :label="s.label" :value="s.key" />
              </el-select>
            </el-form-item>
            <el-form-item label="JD链接">
              <el-input v-model="quickDeliveryForm.link" placeholder="招聘链接" />
            </el-form-item>
            <el-form-item label="标签">
              <el-select-v2
                v-model="quickDeliveryForm.tags"
                :options="[]"
                placeholder="输入标签按回车"
                allow-create
                multiple
                filterable
                style="width: 100%"
              />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="quickDeliveryForm.jd_text" type="textarea" :rows="3" placeholder="岗位描述或匹配原因" />
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="quickDeliveryVisible = false">取消</el-button>
            <el-button type="primary" :loading="quickDeliveryLoading" @click="saveQuickDelivery">保存投递</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>

      <!-- ========== Tab 3: 通知设置 ========== -->
      <el-tab-pane label="通知设置" name="email">
        <RadarEmailSettings v-model:loading="emailLoading" />
      </el-tab-pane>

      <!-- ========== Tab 4: 功能测试 ========== -->
      <el-tab-pane label="功能测试" name="test">
        <div class="test-panel">

          <!-- 测试区域1: 页面抓取测试 -->
          <el-card class="test-card" shadow="never">
            <template #header>
              <div class="test-card-header">
                <span class="test-card-title">1. 页面抓取测试</span>
                <el-tag size="small" type="info">测试网页抓取 + HTML转Markdown</el-tag>
              </div>
            </template>
            <div class="test-card-body">
              <div class="test-form">
                <div class="test-form-row">
                  <el-input
                    v-model="testFetchUrl"
                    placeholder="输入目标网址，如 https://www.zhipin.com/web/geek/job?query=前端"
                    clearable
                    class="test-input"
                  />
                  <el-button
                    type="primary"
                    :loading="testFetchLoading"
                    :icon="CaretRight"
                    @click="runTestFetch"
                  >
                    开始抓取
                  </el-button>
                </div>
                <el-collapse class="test-advanced">
                  <el-collapse-item title="高级选项（自定义请求头）" name="headers">
                    <el-input
                      v-model="testFetchExtraHeaders"
                      type="textarea"
                      :rows="2"
                      placeholder='JSON格式，如 {"Cookie": "..."}'
                    />
                  </el-collapse-item>
                </el-collapse>
              </div>

              <!-- 抓取结果 -->
              <div v-if="testFetchResult" class="test-result">
                <div class="test-result-header">
                  <el-tag :type="testFetchResult.success ? 'success' : 'danger'" size="small">
                    {{ testFetchResult.success ? '成功' : '失败' }}
                  </el-tag>
                  <span class="test-elapsed">耗时 {{ testFetchResult.elapsed_ms }}ms</span>
                  <span class="test-meta">HTTP {{ testFetchResult.status_code }}</span>
                  <span class="test-meta">内容长度 {{ testFetchResult.content_length }} 字符</span>
                  <span v-if="testFetchResult.engine_used" class="test-meta test-engine">
                    引擎: {{ testFetchResult.engine_used }}
                  </span>
                  <el-button
                    v-if="testFetchResult.success && testFetchResult.content"
                    size="small"
                    type="success"
                    plain
                    @click="useFetchResultForAnalyze"
                  >
                    填入分析测试
                  </el-button>
                </div>
                <div v-if="testFetchResult.error" class="test-error">{{ testFetchResult.error }}</div>
                <div v-if="testFetchResult.content" class="test-content-box">
                  <div class="test-content-label">抓取内容预览（Markdown格式）</div>
                  <pre class="test-content-pre">{{ testFetchResult.content.substring(0, 3000) }}{{ testFetchResult.content.length > 3000 ? '\n...(内容过长已截断预览)' : '' }}</pre>
                </div>
              </div>
              <div v-if="testFetchLoading" class="test-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在抓取页面，请稍候...</span>
              </div>
            </div>
          </el-card>

          <!-- 测试区域2: LLM分析测试 -->
          <el-card class="test-card" shadow="never">
            <template #header>
              <div class="test-card-header">
                <span class="test-card-title">2. LLM 分析测试</span>
                <el-tag size="small" type="info">测试AI分析 + 目标匹配</el-tag>
              </div>
            </template>
            <div class="test-card-body">
              <div class="test-form">
                <div class="test-form-row">
                  <el-input
                    v-model="testAnalyzeTarget"
                    placeholder="输入目标描述，如：前端开发实习岗位，薪资8k以上"
                    clearable
                    class="test-input"
                  />
                </div>
                <div class="test-form-row">
                  <el-input
                    v-model="testAnalyzeContent"
                    type="textarea"
                    :rows="6"
                    placeholder="输入页面内容（可从上方抓取测试结果自动填入），或手动粘贴"
                  />
                </div>
                <div class="test-form-actions">
                  <el-button
                    type="primary"
                    :loading="testAnalyzeLoading"
                    :icon="CaretRight"
                    @click="runTestAnalyze"
                  >
                    开始分析
                  </el-button>
                </div>
              </div>

              <!-- 分析结果 -->
              <div v-if="testAnalyzeResult" class="test-result">
                <div class="test-result-header">
                  <el-tag :type="testAnalyzeResult.success ? 'success' : 'danger'" size="small">
                    {{ testAnalyzeResult.success ? '成功' : '失败' }}
                  </el-tag>
                  <span class="test-elapsed">耗时 {{ testAnalyzeResult.elapsed_ms }}ms</span>
                  <el-tag
                    v-if="testAnalyzeResult.analysis?.target_found"
                    type="warning"
                    size="small"
                    effect="dark"
                  >
                    匹配到目标
                  </el-tag>
                  <el-tag v-else-if="testAnalyzeResult.success" type="info" size="small">未匹配</el-tag>
                </div>
                <div v-if="testAnalyzeResult.error" class="test-error">{{ testAnalyzeResult.error }}</div>
                <div v-if="testAnalyzeResult.analysis" class="test-content-box">
                  <div class="test-content-label">分析摘要</div>
                  <p class="test-summary">{{ testAnalyzeResult.analysis.summary || '无摘要' }}</p>
                  <div v-if="testAnalyzeResult.analysis.matched_items?.length" class="test-matched">
                    <div class="test-content-label">匹配职位 ({{ testAnalyzeResult.analysis.matched_items.length }})</div>
                    <el-table :data="testAnalyzeResult.analysis.matched_items" size="small" stripe>
                      <el-table-column prop="company" label="公司" min-width="100" />
                      <el-table-column prop="position" label="岗位" min-width="120" />
                      <el-table-column prop="salary" label="薪资" width="100" />
                      <el-table-column prop="location" label="地点" width="80" />
                      <el-table-column prop="match_reason" label="匹配原因" min-width="150" />
                    </el-table>
                  </div>
                  <div class="test-content-label">完整分析结果</div>
                  <pre class="test-content-pre">{{ JSON.stringify(testAnalyzeResult.analysis, null, 2) }}</pre>
                </div>
              </div>
              <div v-if="testAnalyzeLoading" class="test-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在调用 LLM 分析，请稍候...</span>
              </div>
            </div>
          </el-card>

          <!-- 测试区域3: 全流程一键测试 -->
          <el-card class="test-card" shadow="never">
            <template #header>
              <div class="test-card-header">
                <span class="test-card-title">3. 全流程一键测试</span>
                <el-tag size="small" type="warning">抓取 + 分析全流程</el-tag>
              </div>
            </template>
            <div class="test-card-body">
              <div class="test-form">
                <div class="test-form-row">
                  <el-input
                    v-model="testFullUrl"
                    placeholder="输入目标网址"
                    clearable
                    class="test-input"
                  />
                </div>
                <div class="test-form-row">
                  <el-input
                    v-model="testFullTarget"
                    placeholder="输入目标描述"
                    clearable
                    class="test-input"
                  />
                </div>
                <el-collapse class="test-advanced">
                  <el-collapse-item title="高级选项（自定义请求头）" name="headers">
                    <el-input
                      v-model="testFullExtraHeaders"
                      type="textarea"
                      :rows="2"
                      placeholder='JSON格式'
                    />
                  </el-collapse-item>
                </el-collapse>
                <div class="test-form-actions">
                  <el-button
                    type="primary"
                    :loading="testFullLoading"
                    :icon="CaretRight"
                    @click="runTestFull"
                  >
                    一键测试
                  </el-button>
                </div>
              </div>

              <!-- 全流程结果 -->
              <div v-if="testFullResult" class="test-result">
                <div class="test-result-header">
                  <el-tag :type="testFullResult.success ? 'success' : 'danger'" size="small">
                    {{ testFullResult.success ? '全流程成功' : '失败' }}
                  </el-tag>
                  <span class="test-elapsed">总耗时 {{ testFullResult.total_elapsed_ms }}ms</span>
                </div>

                <!-- Step 1: Fetch -->
                <div class="test-step">
                  <div class="test-step-header">
                    <span class="test-step-label">Step 1: 页面抓取</span>
                    <el-tag :type="testFullResult.fetch.success ? 'success' : 'danger'" size="small">
                      {{ testFullResult.fetch.success ? '成功' : '失败' }}
                    </el-tag>
                    <span class="test-elapsed">{{ testFullResult.fetch.elapsed_ms }}ms</span>
                    <span class="test-meta">HTTP {{ testFullResult.fetch.status_code }}</span>
                    <span class="test-meta">{{ testFullResult.fetch.content_length }} 字符</span>
                    <span v-if="testFullResult.fetch.engine_used" class="test-meta test-engine">
                      引擎: {{ testFullResult.fetch.engine_used }}
                    </span>
                  </div>
                  <div v-if="testFullResult.fetch.error" class="test-error">{{ testFullResult.fetch.error }}</div>
                </div>

                <!-- Step 2: Analyze -->
                <div class="test-step">
                  <div class="test-step-header">
                    <span class="test-step-label">Step 2: LLM 分析</span>
                    <el-tag :type="testFullResult.analyze.success ? 'success' : 'danger'" size="small">
                      {{ testFullResult.analyze.success ? '成功' : '失败' }}
                    </el-tag>
                    <span class="test-elapsed">{{ testFullResult.analyze.elapsed_ms }}ms</span>
                  </div>
                  <div v-if="testFullResult.analyze.error" class="test-error">{{ testFullResult.analyze.error }}</div>
                  <div v-if="testFullResult.analyze.analysis" class="test-content-box">
                    <p class="test-summary">{{ testFullResult.analyze.analysis.summary || '无摘要' }}</p>
                    <div v-if="testFullResult.analyze.analysis.matched_items?.length" class="test-matched">
                      <div class="test-content-label">匹配职位 ({{ testFullResult.analyze.analysis.matched_items.length }})</div>
                      <el-table :data="testFullResult.analyze.analysis.matched_items" size="small" stripe>
                        <el-table-column prop="company" label="公司" min-width="100" />
                        <el-table-column prop="position" label="岗位" min-width="120" />
                        <el-table-column prop="salary" label="薪资" width="100" />
                        <el-table-column prop="location" label="地点" width="80" />
                      </el-table>
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="testFullLoading" class="test-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在执行全流程测试，请稍候...</span>
              </div>
            </div>
          </el-card>

        </div>
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

/* ─── 通用标题 ─── */
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
  color: #64748b;
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
  color: #64748b;
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
  color: #64748b;
  border-bottom: none;
  height: 36px;
  line-height: 36px;
}

.advanced-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
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
  color: #64748b;
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

.no-email { color: #64748b; }

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
}

/* ─── 功能测试面板 ─── */
.test-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.test-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

.test-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.test-card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
}

.test-card-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.test-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.test-form-row {
  display: flex;
  gap: 10px;
}

.test-input {
  flex: 1;
}

.test-form-actions {
  display: flex;
  gap: 10px;
  padding-top: 4px;
}

.test-advanced {
  border: none;
}

.test-advanced :deep(.el-collapse-item__header) {
  font-size: 13px;
  color: #64748b;
  border-bottom: none;
  height: 32px;
  line-height: 32px;
}

.test-advanced :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}

/* 测试结果区域 */
.test-result {
  border-top: 1px solid #e2e8f0;
  padding-top: 16px;
}

.test-result-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.test-elapsed {
  font-size: 13px;
  color: #64748b;
  font-weight: 500;
}

.test-meta {
  font-size: 12px;
  color: #94a3b8;
}

.test-engine {
  color: #409eff;
  font-style: italic;
}

.test-error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 13px;
  color: #dc2626;
  margin-bottom: 12px;
}

.test-content-box {
  margin-top: 8px;
}

.test-content-label {
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  margin-bottom: 6px;
}

.test-content-pre {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.5;
  max-height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  color: #334155;
}

.test-summary {
  font-size: 13px;
  color: #334155;
  line-height: 1.5;
  margin: 0 0 8px 0;
  padding: 8px 12px;
  background: #f0f7ff;
  border-radius: 6px;
  border: 1px solid #dbeafe;
}

.test-matched {
  margin-top: 12px;
}

.test-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 20px;
  color: #64748b;
  font-size: 14px;
}

.test-step {
  margin-top: 16px;
  padding: 12px;
  background: #f8fafc;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
}

.test-step-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.test-step-label {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
}
</style>
