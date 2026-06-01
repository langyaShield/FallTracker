<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)

const handleRegister = async () => {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (password.value !== confirmPassword.value) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  loading.value = true
  try {
    await authStore.register(username.value, password.value)
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <h1 class="login-title">注册账号</h1>
      <p class="login-subtitle">开启你的秋招追踪之旅</p>
      <el-form class="login-form">
        <el-form-item>
          <el-input
            v-model="username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            placeholder="密码"
            size="large"
            :prefix-icon="Lock"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="confirmPassword"
            type="password"
            placeholder="确认密码"
            size="large"
            :prefix-icon="Lock"
            show-password
            @keyup.enter="handleRegister"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="login-btn"
            :loading="loading"
            @click="handleRegister"
          >
            注册
          </el-button>
        </el-form-item>
      </el-form>
      <div class="login-footer">
        <span>已有账号？</span>
        <router-link to="/login" class="register-link">立即登录</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
}

.login-card {
  width: 420px;
  padding: 48px 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(10px);
}

.login-title {
  font-size: 28px;
  font-weight: 700;
  color: #1e3a5f;
  text-align: center;
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 14px;
  color: #64748b;
  text-align: center;
  margin-bottom: 32px;
}

.login-form {
  margin-top: 24px;
}

.login-btn {
  width: 100%;
  background: linear-gradient(135deg, #1e3a5f 0%, #334155 100%);
  border: none;
  font-weight: 600;
}

.login-btn:hover {
  background: linear-gradient(135deg, #152a45 0%, #1e293b 100%);
}

.login-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 14px;
  color: #64748b;
}

.register-link {
  color: #f59e0b;
  font-weight: 600;
  margin-left: 4px;
  text-decoration: none;
}

.register-link:hover {
  color: #d97706;
}
</style>
