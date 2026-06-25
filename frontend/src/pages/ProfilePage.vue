<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete, Select } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'
import PageHeader from '@/components/PageHeader.vue'
import {
  PROFILE_CATEGORY_LABELS,
  PROFILE_BASIC_FIELDS,
  PROFILE_EDUCATION_FIELDS,
  PROFILE_WORK_FIELDS,
  getProfileFieldLabel,
} from '@/lib/constants'

// ─── 数据结构 ───
interface FieldEntry {
  key: string
  value: string
}

interface GroupEntry {
  group_index: number | null  // null = 新增未保存
  fields: FieldEntry[]
}

const loading = ref(false)
const savingCategory = ref<string | null>(null)

// 各分类的数据
const basicFields = ref<FieldEntry[]>([])
const educationGroups = ref<GroupEntry[]>([])
const workGroups = ref<GroupEntry[]>([])

// 自定义字段的输入
const customBasicKey = ref('')

// 当前激活的 Tab
const activeTab = ref('basic')

// 下一个可用的 group_index（从服务端数据推算）
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

    // 计算最大 group_index
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
          // 初始化预设字段
          basicFields.value = PROFILE_BASIC_FIELDS.map(f => ({ key: f.key, value: '' }))
        }
      } else if (cat.category === 'education') {
        educationGroups.value = cat.groups.map(g => ({
          group_index: g.group_index,
          fields: g.fields.map(f => ({ key: f.field_key, value: f.field_value })),
        }))
      } else if (cat.category === 'work') {
        workGroups.value = cat.groups.map(g => ({
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

// ─── 保存分类 ───
const saveCategory = async (category: string) => {
  savingCategory.value = category
  try {
    let groups: Array<{ group_index: number | null; fields: Array<{ field_key: string; field_value: string; sort_order: number }> }>

    if (category === 'basic') {
      groups = [{
        group_index: 0,
        fields: basicFields.value
          .filter(f => f.value.trim())
          .map((f, i) => ({ field_key: f.key, field_value: f.value, sort_order: i })),
      }]
    } else if (category === 'education') {
      groups = educationGroups.value.map(g => ({
        group_index: g.group_index,
        fields: g.fields
          .filter(f => f.value.trim())
          .map((f, i) => ({ field_key: f.key, field_value: f.value, sort_order: i })),
      }))
    } else {
      groups = workGroups.value.map(g => ({
        group_index: g.group_index,
        fields: g.fields
          .filter(f => f.value.trim())
          .map((f, i) => ({ field_key: f.key, field_value: f.value, sort_order: i })),
      }))
    }

    const res = await api.put(`/profile/${category}`, { groups })

    // 更新本地数据（使用服务端返回的 group_index）
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
    } else {
      workGroups.value = resultGroups.map((g: any) => ({
        group_index: g.group_index,
        fields: g.fields.map((f: any) => ({ key: f.field_key, value: f.field_value })),
      }))
    }

    ElMessage.success(`${PROFILE_CATEGORY_LABELS[category]} 保存成功`)
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  } finally {
    savingCategory.value = null
  }
}

// ─── 基本信息操作 ───
const addCustomBasicField = () => {
  const key = customBasicKey.value.trim()
  if (!key) return
  if (basicFields.value.some(f => f.key === key)) {
    ElMessage.warning('该字段已存在')
    return
  }
  basicFields.value.push({ key, value: '' })
  customBasicKey.value = ''
}

const removeBasicField = (index: number) => {
  basicFields.value.splice(index, 1)
}

// 检查一个 key 是否是预设字段
const isPresetBasicKey = (key: string) => PROFILE_BASIC_FIELDS.some(f => f.key === key)

// ─── 教育经历操作 ───
const addEducationGroup = () => {
  educationGroups.value.push({
    group_index: null,
    fields: PROFILE_EDUCATION_FIELDS.map(f => ({ key: f.key, value: '' })),
  })
}

const removeEducationGroup = (index: number) => {
  educationGroups.value.splice(index, 1)
}

// ─── 工作经历操作 ───
const addWorkGroup = () => {
  workGroups.value.push({
    group_index: null,
    fields: PROFILE_WORK_FIELDS.map(f => ({ key: f.key, value: '' })),
  })
}

const removeWorkGroup = (index: number) => {
  workGroups.value.splice(index, 1)
}

// ─── 获取字段标签 ───
const getFieldLabel = (key: string) => getProfileFieldLabel(key)

// 获取教育/工作经历中缺失的预设字段（用于"添加字段"下拉）
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

onMounted(fetchProfile)
</script>

<template>
  <div class="profile-page" v-loading="loading">
    <PageHeader title="个人信息库" />
    <p class="page-desc">预存常用个人信息，在投递官网填写表单时可通过"快捷复制"一键复制，大幅提升填写效率。</p>

    <el-tabs v-model="activeTab" class="profile-tabs">
      <!-- ─── 基本信息 ─── -->
      <el-tab-pane label="基本信息" name="basic">
        <el-card shadow="never" class="section-card">
          <div class="field-grid">
            <div v-for="(field, idx) in basicFields" :key="field.key" class="field-row">
              <div class="field-label">{{ getFieldLabel(field.key) }}</div>
              <div class="field-input">
                <el-input v-model="field.value" :placeholder="getFieldLabel(field.key)" clearable />
              </div>
              <el-button
                v-if="!isPresetBasicKey(field.key)"
                link
                type="danger"
                :icon="Delete"
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

      <!-- ─── 教育经历 ─── -->
      <el-tab-pane label="教育经历" name="education">
        <div v-for="(group, gi) in educationGroups" :key="gi" class="group-card">
          <el-card shadow="never" class="section-card">
            <template #header>
              <div class="group-header">
                <span class="group-title">教育经历 {{ gi + 1 }}</span>
                <el-button link type="danger" :icon="Delete" @click="removeEducationGroup(gi)">删除</el-button>
              </div>
            </template>

            <div class="field-grid">
              <div v-for="(field, fi) in group.fields" :key="field.key" class="field-row">
                <div class="field-label">{{ getFieldLabel(field.key) }}</div>
                <div class="field-input">
                  <el-input
                    v-if="field.key === 'courses' || field.key === 'awards'"
                    v-model="field.value"
                    type="textarea"
                    :rows="2"
                    :placeholder="getFieldLabel(field.key)"
                  />
                  <el-input v-else v-model="field.value" :placeholder="getFieldLabel(field.key)" clearable />
                </div>
                <el-button link type="danger" :icon="Delete" @click="removeFieldFromGroup(group, fi)" />
              </div>
            </div>

            <div class="add-group-field" v-if="getMissingFields(group, PROFILE_EDUCATION_FIELDS).length > 0">
              <el-dropdown trigger="click" @command="(key: string) => addFieldToGroup(group, key)">
                <el-button link type="primary">
                  <el-icon><Plus /></el-icon> 添加字段
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
          </el-card>
        </div>

        <div class="group-actions">
          <el-button :icon="Plus" @click="addEducationGroup">添加教育经历</el-button>
          <el-button
            type="primary"
            :icon="Select"
            :loading="savingCategory === 'education'"
            @click="saveCategory('education')"
          >
            保存教育经历
          </el-button>
        </div>
      </el-tab-pane>

      <!-- ─── 工作经历 ─── -->
      <el-tab-pane label="工作经历" name="work">
        <div v-for="(group, gi) in workGroups" :key="gi" class="group-card">
          <el-card shadow="never" class="section-card">
            <template #header>
              <div class="group-header">
                <span class="group-title">工作经历 {{ gi + 1 }}</span>
                <el-button link type="danger" :icon="Delete" @click="removeWorkGroup(gi)">删除</el-button>
              </div>
            </template>

            <div class="field-grid">
              <div v-for="(field, fi) in group.fields" :key="field.key" class="field-row">
                <div class="field-label">{{ getFieldLabel(field.key) }}</div>
                <div class="field-input">
                  <el-input
                    v-if="field.key === 'description' || field.key === 'achievements'"
                    v-model="field.value"
                    type="textarea"
                    :rows="3"
                    :placeholder="getFieldLabel(field.key)"
                  />
                  <el-input v-else v-model="field.value" :placeholder="getFieldLabel(field.key)" clearable />
                </div>
                <el-button link type="danger" :icon="Delete" @click="removeFieldFromGroup(group, fi)" />
              </div>
            </div>

            <div class="add-group-field" v-if="getMissingFields(group, PROFILE_WORK_FIELDS).length > 0">
              <el-dropdown trigger="click" @command="(key: string) => addFieldToGroup(group, key)">
                <el-button link type="primary">
                  <el-icon><Plus /></el-icon> 添加字段
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="mf in getMissingFields(group, PROFILE_WORK_FIELDS)"
                      :key="mf.key"
                      :command="mf.key"
                    >
                      {{ mf.label }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </el-card>
        </div>

        <div class="group-actions">
          <el-button :icon="Plus" @click="addWorkGroup">添加工作经历</el-button>
          <el-button
            type="primary"
            :icon="Select"
            :loading="savingCategory === 'work'"
            @click="saveCategory('work')"
          >
            保存工作经历
          </el-button>
        </div>
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
  margin: 0 0 20px;
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

.field-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.field-label {
  width: 100px;
  flex-shrink: 0;
  font-size: 14px;
  color: #374151;
  text-align: right;
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
}

@media (max-width: 768px) {
  .field-row {
    flex-wrap: wrap;
  }

  .field-label {
    width: 80px;
    font-size: 13px;
  }
}
</style>
