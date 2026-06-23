<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { CopyDocument, DocumentCopy } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'
import { PROFILE_CATEGORY_LABELS, getProfileFieldLabel } from '@/lib/constants'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const visible = ref(props.modelValue)

watch(() => props.modelValue, (v) => {
  visible.value = v
  if (v) fetchProfile()
})

watch(visible, (v) => {
  emit('update:modelValue', v)
})

// ─── 数据 ───
interface FieldItem {
  field_key: string
  field_value: string
}

interface GroupItem {
  group_index: number
  fields: FieldItem[]
}

interface CategoryItem {
  category: string
  groups: GroupItem[]
}

const loading = ref(false)
const profileData = ref<CategoryItem[]>([])

const fetchProfile = async () => {
  loading.value = true
  try {
    const res = await api.get('/profile')
    profileData.value = res.data || []
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取个人信息失败'))
  } finally {
    loading.value = false
  }
}

// ─── 复制功能 ───
const copyToClipboard = async (text: string, hint?: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(hint ? `已复制: ${hint}` : '已复制到剪贴板')
  } catch {
    // fallback
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success(hint ? `已复制: ${hint}` : '已复制到剪贴板')
  }
}

// 复制单个字段
const copyField = (field: FieldItem) => {
  copyToClipboard(field.field_value, getProfileFieldLabel(field.field_key))
}

// 复制整个分组
const copyGroup = (group: GroupItem) => {
  const text = group.fields
    .map(f => `${getProfileFieldLabel(f.field_key)}：${f.field_value}`)
    .join('\n')
  copyToClipboard(text, '整条信息')
}

// 复制整个分类的所有分组
const copyAllBasic = () => {
  const basic = profileData.value.find(c => c.category === 'basic')
  if (!basic || basic.groups.length === 0) {
    ElMessage.warning('暂无基本信息')
    return
  }
  const text = basic.groups[0].fields
    .map(f => `${getProfileFieldLabel(f.field_key)}：${f.field_value}`)
    .join('\n')
  copyToClipboard(text, '全部基本信息')
}

// ─── 获取分类数据 ───
const getCategory = (name: string) => profileData.value.find(c => c.category === name)

// ─── 教育/工作经历的当前选中分组 ───
const activeEduGroup = ref(0)
const activeWorkGroup = ref(0)
</script>

<template>
  <el-drawer
    v-model="visible"
    title="快捷复制"
    direction="rtl"
    :size="380"
    :destroy-on-close="false"
    class="quick-copy-drawer"
  >
    <div v-loading="loading" class="drawer-body">
      <!-- 基本信息 -->
      <div class="category-section">
        <div class="category-header">
          <span class="category-title">{{ PROFILE_CATEGORY_LABELS.basic || '基本信息' }}</span>
          <el-button
            link
            type="primary"
            :icon="DocumentCopy"
            @click="copyAllBasic"
            :disabled="!getCategory('basic')?.groups[0]?.fields?.length"
          >
            复制全部
          </el-button>
        </div>

        <div v-if="getCategory('basic')?.groups[0]?.fields?.length" class="field-list">
          <div
            v-for="field in getCategory('basic')!.groups[0].fields"
            :key="field.field_key"
            class="field-item"
          >
            <div class="field-info">
              <span class="field-label">{{ getProfileFieldLabel(field.field_key) }}</span>
              <span class="field-value">{{ field.field_value }}</span>
            </div>
            <el-button
              class="copy-btn"
              link
              type="primary"
              :icon="CopyDocument"
              @click="copyField(field)"
            />
          </div>
        </div>
        <div v-else class="empty-hint">暂未填写基本信息</div>
      </div>

      <!-- 教育经历 -->
      <div class="category-section">
        <div class="category-header">
          <span class="category-title">{{ PROFILE_CATEGORY_LABELS.education || '教育经历' }}</span>
          <el-button
            v-if="getCategory('education')?.groups?.length"
            link
            type="primary"
            :icon="DocumentCopy"
            @click="copyGroup(getCategory('education')!.groups[activeEduGroup] || getCategory('education')!.groups[0])"
          >
            复制本条
          </el-button>
        </div>

        <template v-if="getCategory('education')?.groups?.length">
          <el-tabs
            v-if="getCategory('education')!.groups.length > 1"
            v-model="activeEduGroup"
            size="small"
            class="group-tabs"
          >
            <el-tab-pane
              v-for="(g, i) in getCategory('education')!.groups"
              :key="g.group_index"
              :label="`经历 ${i + 1}`"
              :name="i"
            />
          </el-tabs>

          <div class="field-list">
            <div
              v-for="field in (getCategory('education')!.groups[activeEduGroup] || getCategory('education')!.groups[0])?.fields || []"
              :key="field.field_key"
              class="field-item"
            >
              <div class="field-info">
                <span class="field-label">{{ getProfileFieldLabel(field.field_key) }}</span>
                <span class="field-value">{{ field.field_value }}</span>
              </div>
              <el-button
                class="copy-btn"
                link
                type="primary"
                :icon="CopyDocument"
                @click="copyField(field)"
              />
            </div>
          </div>
        </template>
        <div v-else class="empty-hint">暂未填写教育经历</div>
      </div>

      <!-- 工作经历 -->
      <div class="category-section">
        <div class="category-header">
          <span class="category-title">{{ PROFILE_CATEGORY_LABELS.work || '工作经历' }}</span>
          <el-button
            v-if="getCategory('work')?.groups?.length"
            link
            type="primary"
            :icon="DocumentCopy"
            @click="copyGroup(getCategory('work')!.groups[activeWorkGroup] || getCategory('work')!.groups[0])"
          >
            复制本条
          </el-button>
        </div>

        <template v-if="getCategory('work')?.groups?.length">
          <el-tabs
            v-if="getCategory('work')!.groups.length > 1"
            v-model="activeWorkGroup"
            size="small"
            class="group-tabs"
          >
            <el-tab-pane
              v-for="(g, i) in getCategory('work')!.groups"
              :key="g.group_index"
              :label="`经历 ${i + 1}`"
              :name="i"
            />
          </el-tabs>

          <div class="field-list">
            <div
              v-for="field in (getCategory('work')!.groups[activeWorkGroup] || getCategory('work')!.groups[0])?.fields || []"
              :key="field.field_key"
              class="field-item"
            >
              <div class="field-info">
                <span class="field-label">{{ getProfileFieldLabel(field.field_key) }}</span>
                <span class="field-value">{{ field.field_value }}</span>
              </div>
              <el-button
                class="copy-btn"
                link
                type="primary"
                :icon="CopyDocument"
                @click="copyField(field)"
              />
            </div>
          </div>
        </template>
        <div v-else class="empty-hint">暂未填写工作经历</div>
      </div>

      <!-- 底部提示 -->
      <div class="drawer-footer-hint">
        前往 <router-link to="/profile" @click="visible = false">个人信息库</router-link> 编辑数据
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  padding: 0 4px;
}

.category-section {
  margin-bottom: 24px;
}

.category-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #1e3a5f;
}

.category-title {
  font-weight: 700;
  font-size: 15px;
  color: #1e3a5f;
}

.field-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f8fafc;
  border-radius: 6px;
  transition: background 0.15s;
}

.field-item:hover {
  background: #eef2ff;
}

.field-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.field-label {
  font-size: 12px;
  color: #94a3b8;
}

.field-value {
  font-size: 14px;
  color: #1e293b;
  word-break: break-all;
}

.copy-btn {
  flex-shrink: 0;
  margin-left: 8px;
}

.group-tabs {
  margin-bottom: 8px;
}

.group-tabs :deep(.el-tabs__item) {
  font-size: 12px;
  height: 28px;
  line-height: 28px;
}

.empty-hint {
  font-size: 13px;
  color: #94a3b8;
  padding: 12px 0;
  text-align: center;
}

.drawer-footer-hint {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
  font-size: 12px;
  color: #94a3b8;
  text-align: center;
}

.drawer-footer-hint a {
  color: #1e3a5f;
  font-weight: 600;
  text-decoration: none;
}

.drawer-footer-hint a:hover {
  text-decoration: underline;
}
</style>
