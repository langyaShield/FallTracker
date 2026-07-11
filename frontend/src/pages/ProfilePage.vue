<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, Select, Edit, Close, Search } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'
import {
  PROFILE_CATEGORY_LABELS,
  PROFILE_BASIC_FIELDS,
  PROFILE_EDUCATION_FIELDS,
  getProfileFieldLabel,
  getCategoryFieldLabel,
} from '@/lib/constants'

// ─── 数据结构 ───
interface FieldEntry {
  key: string
  value: string
}

interface GroupEntry {
  group_index: number | null
  fields: FieldEntry[]
}

const loading = ref(false)
const savingCategory = ref<string | null>(null)

const editingCategory = ref<string | null>(null)
const editBasicFields = ref<FieldEntry[]>([])
const editEducationGroups = ref<GroupEntry[]>([])

const basicFields = ref<FieldEntry[]>([])
const educationGroups = ref<GroupEntry[]>([])

const customBasicKey = ref('')
const activeTab = ref('basic')

// ─── 全局搜索 ───
const searchQuery = ref('')

const hasSearchResults = computed(() => {
  if (!searchQuery.value) return true
  const q = searchQuery.value.toLowerCase()
  const basicMatch = basicFields.value.some(f => {
    const label = getFieldLabel(f.key).toLowerCase()
    return label.includes(q) || f.value.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
  })
  const eduMatch = educationGroups.value.some(g =>
    g.fields.some(f => {
      const label = getCategoryFieldLabel('education', f.key).toLowerCase()
      return label.includes(q) || f.value.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
    })
  )
  return basicMatch || eduMatch
})

const filteredBasicFields = computed(() => {
  if (!searchQuery.value) return basicFields.value
  const q = searchQuery.value.toLowerCase()
  return basicFields.value.filter(f => {
    const label = getFieldLabel(f.key).toLowerCase()
    return label.includes(q) || f.value.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
  })
})

const filteredEducationGroups = computed(() => {
  if (!searchQuery.value) return educationGroups.value
  const q = searchQuery.value.toLowerCase()
  return educationGroups.value.filter(g =>
    g.fields.some(f => {
      const label = getCategoryFieldLabel('education', f.key).toLowerCase()
      return label.includes(q) || f.value.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
    })
  ).map(g => ({
    ...g,
    fields: g.fields.filter(f => {
      const label = getCategoryFieldLabel('education', f.key).toLowerCase()
      return label.includes(q) || f.value.toLowerCase().includes(q) || f.key.toLowerCase().includes(q)
    }),
  }))
})

let nextGroupIndex = 100

// ─── 加载数据 ───
const fetchProfile = async () => {
  loading.value = true
  try {
    const res = await api.get('/profile')
    const categories = res.data as Array<{
      category: string
      groups: Array<{
        group_index: number
        fields: Array<{ field_key: string; field_value: string; sort_order: number }>
      }>
    }>

    let maxGi = 0
    for (const cat of categories) {
      for (const g of cat.groups) {
        if (g.group_index > maxGi) maxGi = g.group_index
      }
    }
    nextGroupIndex = maxGi + 1

    for (const cat of categories) {
      if (cat.category === 'basic') {
        if (cat.groups.length > 0) {
          basicFields.value = cat.groups[0].fields.map(f => ({
            key: f.field_key,
            value: f.field_value,
          }))
        } else {
          basicFields.value = PROFILE_BASIC_FIELDS.map(f => ({ key: f.key, value: '' }))
        }
      } else if (cat.category === 'education') {
        educationGroups.value = cat.groups.map(g => ({
          group_index: g.group_index,
          fields: g.fields.map(f => ({ key: f.field_key, value: f.field_value })),
        }))
      }
    }
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取个人信息失败'))
  } finally {
    loading.value = false
  }
}

// ─── 进入编辑模式 ───
const enterEdit = (category: string) => {
  searchQuery.value = ''
  if (category === 'basic') {
    editBasicFields.value = basicFields.value.map(f => ({ ...f }))
  } else {
    editEducationGroups.value = educationGroups.value.map(g => ({
      group_index: g.group_index,
      fields: g.fields.map(f => ({ ...f })),
    }))
  }
  editingCategory.value = category
}

const cancelEdit = () => {
  editingCategory.value = null
}

// ─── 保存分类 ───
const saveCategory = async (category: string) => {
  savingCategory.value = category
  try {
    let groups: Array<{ group_index: number | null; fields: Array<{ field_key: string; field_value: string; sort_order: number }> }> = []

    if (category === 'basic') {
      groups = [{
        group_index: 0,
        fields: editBasicFields.value
          .filter(f => f.value.trim())
          .map((f, i) => ({ field_key: f.key, field_value: f.value, sort_order: i })),
      }]
    } else if (category === 'education') {
      groups = editEducationGroups.value.map(g => ({
        group_index: g.group_index,
        fields: g.fields
          .filter(f => f.value.trim())
          .map((f, i) => ({ field_key: f.key, field_value: f.value, sort_order: i })),
      }))
    }

    const res = await api.put(`/profile/${category}`, { groups })

    const resultGroups = res.data.groups || []
    if (category === 'basic') {
      if (resultGroups.length > 0) {
        basicFields.value = resultGroups[0].fields.map((f: any) => ({
          key: f.field_key,
          value: f.field_value,
        }))
      }
    } else if (category === 'education') {
      educationGroups.value = resultGroups.map((g: any) => ({
        group_index: g.group_index,
        fields: g.fields.map((f: any) => ({ key: f.field_key, value: f.field_value })),
      }))
    }

    editingCategory.value = null
    ElMessage.success(`${PROFILE_CATEGORY_LABELS[category]} 保存成功`)
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  } finally {
    savingCategory.value = null
  }
}

// ─── 编辑模式下的操作 ───
const addCustomBasicField = () => {
  const key = customBasicKey.value.trim()
  if (!key) return
  if (editBasicFields.value.some(f => f.key === key)) {
    ElMessage.warning('该字段已存在')
    return
  }
  editBasicFields.value.push({ key, value: '' })
  customBasicKey.value = ''
}

const removeBasicField = (index: number) => {
  editBasicFields.value.splice(index, 1)
}

const isPresetBasicKey = (key: string) => PROFILE_BASIC_FIELDS.some(f => f.key === key)

const addEducationGroup = () => {
  editEducationGroups.value.push({
    group_index: null,
    fields: PROFILE_EDUCATION_FIELDS.map(f => ({ key: f.key, value: '' })),
  })
}

const removeEducationGroup = (index: number) => {
  editEducationGroups.value.splice(index, 1)
}

const getFieldLabel = (key: string) => getProfileFieldLabel(key)

const getMissingFields = (group: GroupEntry, presetFields: Array<{ key: string; label: string }>) => {
  const existingKeys = new Set(group.fields.map(f => f.key))
  return presetFields.filter(f => !existingKeys.has(f.key))
}

const addFieldToGroup = (group: GroupEntry, key: string) => {
  group.fields.push({ key, value: '' })
}

const removeFieldFromGroup = (group: GroupEntry, index: number) => {
  group.fields.splice(index, 1)
}

// ─── 教育经历自定义字段 ───
const customFieldKeys = ref<Record<string, string>>({})
const customFieldValues = ref<Record<string, string>>({})

const addCustomFieldToGroup = (group: GroupEntry, gi: number) => {
  const key = (customFieldKeys.value[gi] || '').trim()
  const value = (customFieldValues.value[gi] || '').trim()
  if (!key) {
    ElMessage.warning('请输入字段名')
    return
  }
  if (group.fields.some(f => f.key === key)) {
    ElMessage.warning('该字段已存在')
    return
  }
  group.fields.push({ key, value })
  customFieldKeys.value[gi] = ''
  customFieldValues.value[gi] = ''
}

// ─── 拖拽排序 ───
const dragSource = ref<{ groupIdx: number; fieldIdx: number } | null>(null)
const dragTarget = ref<{ groupIdx: number; fieldIdx: number } | null>(null)

const onDragStartBasic = (idx: number) => {
  dragSource.value = { groupIdx: -1, fieldIdx: idx }
}

const onDragOverBasic = (e: DragEvent, idx: number) => {
  e.preventDefault()
  dragTarget.value = { groupIdx: -1, fieldIdx: idx }
}

const onDropBasic = () => {
  if (!dragSource.value || !dragTarget.value) return
  const src = dragSource.value.fieldIdx
  const dst = dragTarget.value.fieldIdx
  if (src === dst) return
  const item = editBasicFields.value.splice(src, 1)[0]
  editBasicFields.value.splice(dst, 0, item)
  dragSource.value = null
  dragTarget.value = null
}

const onDragStartEdu = (gi: number, fi: number) => {
  dragSource.value = { groupIdx: gi, fieldIdx: fi }
}

const onDragOverEdu = (e: DragEvent, gi: number, fi: number) => {
  e.preventDefault()
  dragTarget.value = { groupIdx: gi, fieldIdx: fi }
}

const onDropEdu = (gi: number) => {
  if (!dragSource.value || !dragTarget.value) return
  if (dragSource.value.groupIdx !== gi || dragTarget.value.groupIdx !== gi) return
  const src = dragSource.value.fieldIdx
  const dst = dragTarget.value.fieldIdx
  if (src === dst) return
  const group = editEducationGroups.value[gi]
  const item = group.fields.splice(src, 1)[0]
  group.fields.splice(dst, 0, item)
  dragSource.value = null
  dragTarget.value = null
}

// ─── 复制到剪贴板 ───
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    ElMessage.success('已复制')
  }
}

onMounted(fetchProfile)
</script>

<template>
  <div class="profile-page" v-loading="loading">
    <PageHeader title="个人信息库" />
    <p class="page-desc">预存常用个人信息，在投递官网填写表单时可通过点击字段值一键复制，大幅提升填写效率。</p>

    <!-- 全局搜索（查看模式时） -->
    <div class="search-bar" v-if="editingCategory === null">
      <el-input
        v-model="searchQuery"
        placeholder="全局搜索字段名或值..."
        :prefix-icon="Search"
        clearable
        class="profile-search"
      />
    </div>

    <el-tabs v-model="activeTab" class="profile-tabs">
      <!-- ═══════════════ 基本信息 ═══════════════ -->
      <el-tab-pane label="基本信息" name="basic">
        <!-- 查看模式 -->
        <el-card v-if="editingCategory !== 'basic'" shadow="never" class="section-card">
          <div class="field-grid">
            <div v-for="field in filteredBasicFields" :key="field.key" class="field-row">
              <div class="field-label">{{ getFieldLabel(field.key) }}</div>
              <div class="field-value" :class="{ 'field-empty': !field.value }" @click="field.value && copyToClipboard(field.value)">
                {{ field.value || '-' }}
              </div>
            </div>
          </div>
          <div v-if="filteredBasicFields.length === 0 && !searchQuery" class="empty-hint">暂无信息，点击下方按钮开始编辑</div>
          <div v-else-if="filteredBasicFields.length === 0" class="empty-hint">基本信息中没有匹配的字段</div>
          <div class="save-section">
            <el-button type="primary" :icon="Edit" @click="enterEdit('basic')">编辑基本信息</el-button>
          </div>
        </el-card>

        <!-- 编辑模式 -->
        <el-card v-else shadow="never" class="section-card">
          <div class="edit-hint">
            <el-icon><Edit /></el-icon> 拖拽左侧手柄可调整字段顺序
          </div>
          <div class="field-grid">
            <div
              v-for="(field, idx) in editBasicFields"
              :key="field.key"
              class="field-row"
              :class="{ 'drag-over': dragTarget?.groupIdx === -1 && dragTarget?.fieldIdx === idx }"
              draggable="true"
              @dragstart="onDragStartBasic(idx)"
              @dragover="(e: DragEvent) => onDragOverBasic(e, idx)"
              @drop="onDropBasic"
              @dragend="dragSource = null; dragTarget = null"
            >
              <div class="drag-handle" title="拖动排序">⠿</div>
              <div class="field-label">{{ getFieldLabel(field.key) }}</div>
              <div class="field-input">
                <el-input v-model="field.value" :placeholder="getFieldLabel(field.key)" clearable />
              </div>
              <el-button
                v-if="!isPresetBasicKey(field.key)"
                link
                type="danger"
                :icon="Delete"
                aria-label="删除字段"
                @click="removeBasicField(idx)"
              />
            </div>
          </div>

          <div class="add-custom-field">
            <el-input
              v-model="customBasicKey"
              placeholder="自定义字段名（如：紧急联系人）"
              style="max-width: 240px"
              @keyup.enter="addCustomBasicField"
            >
              <template #append>
                <el-button :icon="Plus" @click="addCustomBasicField">添加</el-button>
              </template>
            </el-input>
          </div>

          <div class="save-section">
            <el-button :icon="Close" @click="cancelEdit">取消</el-button>
            <el-button
              type="primary"
              :icon="Select"
              :loading="savingCategory === 'basic'"
              @click="saveCategory('basic')"
            >
              保存基本信息
            </el-button>
          </div>
        </el-card>
      </el-tab-pane>

      <!-- ═══════════════ 教育经历 ═══════════════ -->
      <el-tab-pane label="教育经历" name="education">
        <!-- 查看模式 -->
        <template v-if="editingCategory !== 'education'">
          <div v-for="(group, gi) in filteredEducationGroups" :key="gi" class="group-card">
            <el-card shadow="never" class="section-card">
              <template #header>
                <div class="group-header">
                  <span class="group-title">教育经历 {{ gi + 1 }}</span>
                </div>
              </template>
              <div class="field-grid">
                <div v-for="field in group.fields" :key="field.key" class="field-row">
                  <div class="field-label">{{ getCategoryFieldLabel('education', field.key) }}</div>
                  <div class="field-value" :class="{ 'field-empty': !field.value }" @click="field.value && copyToClipboard(field.value)">
                    {{ field.value || '-' }}
                  </div>
                </div>
              </div>
            </el-card>
          </div>
          <div v-if="filteredEducationGroups.length === 0 && !searchQuery" class="empty-hint">暂无教育经历，点击下方按钮开始编辑</div>
          <div v-else-if="filteredEducationGroups.length === 0" class="empty-hint">教育经历中没有匹配的内容</div>
          <div class="save-section">
            <el-button type="primary" :icon="Edit" @click="enterEdit('education')">编辑教育经历</el-button>
          </div>
        </template>

        <!-- 编辑模式 -->
        <template v-else>
          <div v-for="(group, gi) in editEducationGroups" :key="gi" class="group-card">
            <el-card shadow="never" class="section-card">
              <template #header>
                <div class="group-header">
                  <span class="group-title">教育经历 {{ gi + 1 }}</span>
                  <el-button link type="danger" :icon="Delete" @click="removeEducationGroup(gi)">删除</el-button>
                </div>
              </template>

              <div class="edit-hint">
                <el-icon><Edit /></el-icon> 拖拽左侧手柄可调整字段顺序
              </div>
              <div class="field-grid">
                <div
                  v-for="(field, fi) in group.fields"
                  :key="field.key"
                  class="field-row"
                  :class="{ 'drag-over': dragTarget?.groupIdx === gi && dragTarget?.fieldIdx === fi }"
                  draggable="true"
                  @dragstart="onDragStartEdu(gi, fi)"
                  @dragover="(e: DragEvent) => onDragOverEdu(e, gi, fi)"
                  @drop="onDropEdu(gi)"
                  @dragend="dragSource = null; dragTarget = null"
                >
                  <div class="drag-handle" title="拖动排序">⠿</div>
                  <div class="field-label">{{ getCategoryFieldLabel('education', field.key) }}</div>
                  <div class="field-input">
                    <el-input
                      v-if="field.key === 'courses' || field.key === 'awards'"
                      v-model="field.value"
                      type="textarea"
                      :rows="2"
                      :placeholder="getCategoryFieldLabel('education', field.key)"
                    />
                    <el-input v-else v-model="field.value" :placeholder="getCategoryFieldLabel('education', field.key)" clearable />
                  </div>
                  <el-button link type="danger" :icon="Delete" aria-label="删除字段" @click="removeFieldFromGroup(group, fi)" />
                </div>
              </div>

              <div class="add-group-field" v-if="getMissingFields(group, PROFILE_EDUCATION_FIELDS).length > 0">
                <el-dropdown trigger="click" @command="(key: string) => addFieldToGroup(group, key)">
                  <el-button link type="primary">
                    <el-icon><Plus /></el-icon> 添加预设字段
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item
                        v-for="mf in getMissingFields(group, PROFILE_EDUCATION_FIELDS)"
                        :key="mf.key"
                        :command="mf.key"
                      >
                        {{ mf.label }}
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>

              <div class="add-custom-field-inline">
                <el-input
                  :model-value="customFieldKeys[gi] || ''"
                  placeholder="字段名（如：导师）"
                  style="width: 140px"
                  @input="(val: string) => customFieldKeys[gi] = val"
                  @keyup.enter="addCustomFieldToGroup(group, gi)"
                />
                <el-input
                  :model-value="customFieldValues[gi] || ''"
                  placeholder="字段值"
                  style="flex: 1"
                  @input="(val: string) => customFieldValues[gi] = val"
                  @keyup.enter="addCustomFieldToGroup(group, gi)"
                />
                <el-button :icon="Plus" @click="addCustomFieldToGroup(group, gi)">添加</el-button>
              </div>
            </el-card>
          </div>

          <div class="group-actions">
            <el-button :icon="Plus" @click="addEducationGroup">添加教育经历</el-button>
            <el-button :icon="Close" @click="cancelEdit">取消</el-button>
            <el-button
              type="primary"
              :icon="Select"
              :loading="savingCategory === 'education'"
              @click="saveCategory('education')"
            >
              保存教育经历
            </el-button>
          </div>
        </template>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.profile-page {
  height: 100%;
}

.page-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0 0 16px;
}

.search-bar {
  margin-bottom: 16px;
  max-width: 400px;
}

.profile-tabs {
  max-width: 860px;
}

.section-card {
  margin-bottom: 16px;
}

.section-card :deep(.el-card__header) {
  padding: 12px 20px;
}

.edit-hint {
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.field-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px 4px;
  border-radius: 6px;
  transition: background 0.15s;
}

.field-row.drag-over {
  background: #e0f2fe;
}

.drag-handle {
  cursor: grab;
  color: #94a3b8;
  font-size: 16px;
  user-select: none;
  flex-shrink: 0;
  padding: 2px 0;
  line-height: 1;
}

.drag-handle:active {
  cursor: grabbing;
}

.field-label {
  width: 80px;
  flex-shrink: 0;
  font-size: 14px;
  color: #374151;
  text-align: right;
}

.field-value {
  flex: 1;
  font-size: 14px;
  color: #1e3a5f;
  padding: 6px 10px;
  background: #f8fafc;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  min-height: 34px;
  display: flex;
  align-items: center;
}

.field-value:hover {
  background: #e0f2fe;
}

.field-empty {
  color: #cbd5e1;
  cursor: default;
}

.field-empty:hover {
  background: #f8fafc;
}

.field-input {
  flex: 1;
  min-width: 0;
}

.add-custom-field {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #e2e8f0;
}

.add-custom-field-inline {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e2e8f0;
  align-items: center;
}

.add-group-field {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #e2e8f0;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.group-title {
  font-weight: 600;
  font-size: 15px;
  color: #1e3a5f;
}

.group-card {
  margin-bottom: 12px;
}

.group-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}

.save-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  gap: 10px;
}

.empty-hint {
  text-align: center;
  color: #94a3b8;
  font-size: 14px;
  padding: 32px 0;
}

@media (max-width: 768px) {
  .field-row {
    flex-wrap: wrap;
  }

  .field-label {
    width: 60px;
    font-size: 13px;
  }

  .add-custom-field-inline {
    flex-wrap: wrap;
  }

  .drag-handle {
    order: -1;
  }
}
</style>
