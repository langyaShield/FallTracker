<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, ArrowLeft } from '@element-plus/icons-vue'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'

const router = useRouter()

const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const loading = ref(false)

const passwordMismatch = computed(() => {
  return confirmPassword.value.length > 0 && newPassword.value !== confirmPassword.value
})

const handleSubmit = async () => {
  if (!oldPassword.value || !newPassword.value || !confirmPassword.value) {
    ElMessage.warning('请填写所有密码字段')
    return
  }
  if (newPassword.value.length < 6 || newPassword.value.length > 128) {
    ElMessage.warning('新密码长度应为 6-128 位')
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的新密码不一致')
    return
  }
  loading.value = true
  try {
    await api.put('/auth/change-password', {
      old_password: oldPassword.value,
      new_password: newPassword.value,
      confirm_password: confirmPassword.value,
    })
    ElMessage.success('密码修改成功')
    router.push('/dashboard')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '密码修改失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="change-password-page">
    <div class="cp-card">
      <div class="cp-header">
        <el-button text :icon="ArrowLeft" @click="router.back()">返回</el-button>
        <h2>修改密码</h2>
      </div>

      <el-form class="cp-form" label-width="100px">
        <el-form-item label="旧密码">
          <el-input
            v-model="oldPassword"
            type="password"
            placeholder="输入当前密码"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input
            v-model="newPassword"
            type="password"
            placeholder="输入新密码（6-128位）"
            maxlength="128"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-form-item label="确认新密码" :error="passwordMismatch ? '两次输入的密码不一致' : ''">
          <el-input
            v-model="confirmPassword"
            type="password"
            maxlength="128"
            placeholder="再次输入新密码"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleSubmit"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            @click="handleSubmit"
            style="width: 100%"
          >
            确认修改
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.change-password-page {
  display: flex;
  justify-content: center;
  padding-top: 40px;
}

.cp-card {
  max-width: 480px;
  width: 90%;
  background: #fff;
  border-radius: 12px;
  padding: 32px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.cp-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 32px;
}

.cp-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1e3a5f;
}

.cp-form {
  margin-top: 8px;
}

@media (max-width: 768px) {
  .change-password-page {
    padding-top: 20px;
  }

  .cp-card {
    padding: 20px 16px;
  }

  .cp-header h2 {
    font-size: 18px;
  }
}
</style>
