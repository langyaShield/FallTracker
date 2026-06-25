<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Link, Edit, Delete } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'

interface BookmarkItem {
  id: number
  title: string
  url: string
  category: string
  icon: string
  sort_order: number
  created_at: string | null
}

const bookmarks = ref<BookmarkItem[]>([])
const loading = ref(false)
const dialogVisible = ref(false)
const editingBookmark = ref<BookmarkItem | null>(null)

const form = ref({
  title: '',
  url: '',
  category: '',
  icon: '',
  sort_order: 0,
})

const categories = computed(() => {
  const cats = new Set(bookmarks.value.map(b => b.category).filter(c => c))
  return ['', ...Array.from(cats).sort()]
})

const groupedBookmarks = computed(() => {
  const groups: Record<string, BookmarkItem[]> = {}
  for (const b of bookmarks.value) {
    const cat = b.category || '未分类'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(b)
  }
  return groups
})

const fetchBookmarks = async () => {
  loading.value = true
  try {
    const res = await api.get('/bookmarks')
    bookmarks.value = res.data || []
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '加载书签失败'))
  } finally {
    loading.value = false
  }
}

const openAddDialog = () => {
  editingBookmark.value = null
  form.value = { title: '', url: '', category: '', icon: '', sort_order: 0 }
  dialogVisible.value = true
}

const openEditDialog = (bookmark: BookmarkItem) => {
  editingBookmark.value = bookmark
  form.value = {
    title: bookmark.title,
    url: bookmark.url,
    category: bookmark.category,
    icon: bookmark.icon,
    sort_order: bookmark.sort_order,
  }
  dialogVisible.value = true
}

const submitForm = async () => {
  if (!form.value.title.trim()) {
    ElMessage.warning('请输入网站名称')
    return
  }
  if (!form.value.url.trim()) {
    ElMessage.warning('请输入网址链接')
    return
  }
  // 自动补全 http://
  if (!/^https?:\/\//i.test(form.value.url)) {
    form.value.url = 'https://' + form.value.url
  }

  try {
    if (editingBookmark.value) {
      await api.put(`/bookmarks/${editingBookmark.value.id}`, form.value)
      ElMessage.success('书签已更新')
    } else {
      await api.post('/bookmarks', form.value)
      ElMessage.success('书签已添加')
    }
    dialogVisible.value = false
    fetchBookmarks()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  }
}

const deleteBookmark = async (bookmark: BookmarkItem) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除书签"${bookmark.title}"吗？`,
      '删除确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await api.delete(`/bookmarks/${bookmark.id}`)
    ElMessage.success('已删除')
    fetchBookmarks()
  } catch (e: unknown) {
    ElMessage.error(extractErrorMessage(e, '删除失败'))
  }
}

const openLink = (url: string) => {
  window.open(url, '_blank', 'noopener,noreferrer')
}

const getDomain = (url: string): string => {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

const getFaviconUrl = (url: string): string => {
  try {
    const domain = new URL(url).origin
    return `${domain}/favicon.ico`
  } catch {
    return ''
  }
}

onMounted(() => {
  fetchBookmarks()
})
</script>

<template>
  <div class="bookmarks-page" v-loading="loading">
    <div class="page-header">
      <h2>常用网站</h2>
      <el-button type="primary" :icon="Plus" @click="openAddDialog">添加书签</el-button>
    </div>

    <div v-if="bookmarks.length === 0 && !loading" class="empty-state">
      <el-empty description="还没有添加任何书签">
        <el-button type="primary" @click="openAddDialog">添加第一个书签</el-button>
      </el-empty>
    </div>

    <div v-for="(items, category) in groupedBookmarks" :key="category" class="bookmark-group">
      <h3 class="group-title">{{ category }}</h3>
      <div class="bookmark-grid">
        <div
          v-for="bookmark in items"
          :key="bookmark.id"
          class="bookmark-card"
          @click="openLink(bookmark.url)"
        >
          <div class="card-content">
            <div class="bookmark-icon">
              <span v-if="bookmark.icon" class="emoji-icon">{{ bookmark.icon }}</span>
              <img
                v-else
                :src="getFaviconUrl(bookmark.url)"
                @error="($event.target as HTMLImageElement).style.display = 'none'"
                class="favicon"
                alt=""
              />
              <Link v-if="!bookmark.icon" class="fallback-icon" />
            </div>
            <div class="bookmark-info">
              <div class="bookmark-title">{{ bookmark.title }}</div>
              <div class="bookmark-url">{{ getDomain(bookmark.url) }}</div>
            </div>
          </div>
          <div class="card-actions" @click.stop>
            <el-button text size="small" :icon="Edit" @click="openEditDialog(bookmark)" />
            <el-button text size="small" type="danger" :icon="Delete" @click="deleteBookmark(bookmark)" />
          </div>
        </div>
      </div>
    </div>

    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingBookmark ? '编辑书签' : '添加书签'"
      width="480px"
      @close="form = { title: '', url: '', category: '', icon: '', sort_order: 0 }"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="网站名称" required>
          <el-input v-model="form.title" placeholder="如：BOSS直聘" />
        </el-form-item>
        <el-form-item label="网址" required>
          <el-input v-model="form.url" placeholder="如：https://www.zhipin.com" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="如：招聘平台（可选）" />
        </el-form-item>
        <el-form-item label="图标">
          <el-input v-model="form.icon" placeholder="输入 emoji 如：💼（可选）" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">
          {{ editingBookmark ? '保存' : '添加' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.bookmarks-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-header h2 {
  font-size: 24px;
  font-weight: 700;
  color: #1e3a5f;
  margin: 0;
}

.empty-state {
  padding: 60px 0;
}

.bookmark-group {
  margin-bottom: 32px;
}

.group-title {
  font-size: 16px;
  font-weight: 600;
  color: #334155;
  margin: 0 0 16px 0;
  padding-bottom: 8px;
  border-bottom: 2px solid #e2e8f0;
}

.bookmark-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.bookmark-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bookmark-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  border-color: #1e3a5f;
  transform: translateY(-2px);
}

.card-content {
  display: flex;
  align-items: center;
  gap: 12px;
}

.bookmark-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  position: relative;
}

.emoji-icon {
  font-size: 24px;
}

.favicon {
  width: 24px;
  height: 24px;
  border-radius: 4px;
}

.fallback-icon {
  width: 20px;
  height: 20px;
  color: #94a3b8;
  position: absolute;
  z-index: -1;
}

.bookmark-info {
  flex: 1;
  min-width: 0;
}

.bookmark-title {
  font-size: 15px;
  font-weight: 600;
  color: #1e3a5f;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bookmark-url {
  font-size: 12px;
  color: #94a3b8;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}

.card-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
  align-self: flex-end;
}

.bookmark-card:hover .card-actions {
  opacity: 1;
}

@media (max-width: 768px) {
  .bookmark-grid {
    grid-template-columns: 1fr;
    gap: 12px;
  }

  .page-header h2 {
    font-size: 20px;
  }

  .card-actions {
    opacity: 1;
  }
}

@media (max-width: 480px) {
  .bookmarks-page {
    padding: 0;
  }

  .bookmark-card {
    padding: 12px;
  }
}
</style>
