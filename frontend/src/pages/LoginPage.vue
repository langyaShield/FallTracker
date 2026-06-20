<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { extractErrorMessage } from '@/lib/error'

const router = useRouter()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)

const handleLogin = async () => {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await authStore.login(username.value, password.value)
    ElMessage.success('登录成功')
    router.push('/dashboard')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '登录失败'))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-container">
    <!-- 动态几何背景 -->
    <div class="auth-bg">
      <div class="bg-shape bg-shape-1"></div>
      <div class="bg-shape bg-shape-2"></div>
      <div class="bg-shape bg-shape-3"></div>
      <div class="bg-shape bg-shape-4"></div>
      <div class="bg-shape bg-shape-5"></div>
      <div class="bg-shape bg-shape-6"></div>
      <div class="bg-dots"></div>
    </div>

    <div class="auth-card">
      <h1 class="auth-title">秋招智能追踪系统</h1>
      <p class="auth-subtitle">FallTracker - 你的求职效率引擎</p>
      <el-form class="auth-form">
        <el-form-item>
          <el-input
            v-model="username"
            placeholder="用户名"
            size="large"
            :prefix-icon="User"
            @keyup.enter="handleLogin"
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
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            class="auth-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="auth-footer">
        <span>还没有账号？</span>
        <router-link to="/register" class="auth-link">立即注册</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-container {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0b1120;
  overflow: hidden;
}

/* ===== 动态几何背景 ===== */
.auth-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 0;
}

.bg-shape {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
}

.bg-shape-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(245, 158, 11, 0.5), rgba(245, 158, 11, 0.05));
  top: -10%; left: -5%;
  animation: orbit1 18s ease-in-out infinite;
}

.bg-shape-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.45), rgba(59, 130, 246, 0.05));
  bottom: -5%; right: -5%;
  animation: orbit2 22s ease-in-out infinite;
}

.bg-shape-3 {
  width: 300px; height: 300px;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.4), rgba(16, 185, 129, 0.05));
  top: 50%; left: 60%;
  animation: orbit3 16s ease-in-out infinite;
}

.bg-shape-4 {
  width: 350px; height: 350px;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.4), rgba(139, 92, 246, 0.05));
  top: 15%; left: 50%;
  animation: orbit4 20s ease-in-out infinite;
}

.bg-shape-5 {
  width: 280px; height: 280px;
  background: radial-gradient(circle, rgba(236, 72, 153, 0.4), rgba(236, 72, 153, 0.05));
  bottom: 20%; left: 15%;
  animation: orbit1 14s ease-in-out infinite reverse;
}

.bg-shape-6 {
  width: 220px; height: 220px;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.45), rgba(6, 182, 212, 0.05));
  top: 70%; left: 35%;
  animation: orbit2 17s ease-in-out infinite reverse;
}

/* 流动光线条纹 */
.bg-stripes {
  position: absolute;
  inset: -50%;
  background: repeating-linear-gradient(
    45deg,
    transparent,
    transparent 80px,
    rgba(255, 255, 255, 0.015) 80px,
    rgba(255, 255, 255, 0.015) 81px
  );
  animation: stripeSlide 40s linear infinite;
}

/* 网格点阵 */
.bg-dots {
  position: absolute;
  inset: 0;
  background-image: radial-gradient(circle, rgba(255,255,255,0.12) 1px, transparent 1px);
  background-size: 50px 50px;
  animation: dotsMove 25s linear infinite;
}

/* ===== 动画关键帧 ===== */
@keyframes orbit1 {
  0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); }
  25%  { transform: translate(80px, -50px) scale(1.25) rotate(5deg); }
  50%  { transform: translate(-40px, 40px) scale(0.85) rotate(-3deg); }
  75%  { transform: translate(50px, 20px) scale(1.15) rotate(2deg); }
}

@keyframes orbit2 {
  0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); }
  33%  { transform: translate(-60px, -40px) scale(1.3) rotate(-5deg); }
  66%  { transform: translate(40px, 50px) scale(0.8) rotate(3deg); }
}

@keyframes orbit3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50%  { transform: translate(-70px, 30px) scale(1.35); }
}

@keyframes orbit4 {
  0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); }
  50%  { transform: translate(50px, -40px) scale(1.2) rotate(8deg); }
}

@keyframes stripeSlide {
  0% { transform: translate(0, 0); }
  100% { transform: translate(80px, 80px); }
}

@keyframes dotsMove {
  0% { background-position: 0 0; }
  100% { background-position: 50px 50px; }
}

/* 卡片 */
.auth-card {
  position: relative;
  z-index: 1;
  width: 420px;
  padding: 48px 40px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35), 0 0 120px rgba(59, 130, 246, 0.08);
  backdrop-filter: blur(10px);
}

.auth-title {
  font-size: 28px;
  font-weight: 700;
  color: #1e3a5f;
  text-align: center;
  margin-bottom: 8px;
}

.auth-subtitle {
  font-size: 14px;
  color: #64748b;
  text-align: center;
  margin-bottom: 32px;
}

.auth-form {
  margin-top: 24px;
}

.auth-btn {
  width: 100%;
  background: linear-gradient(135deg, #1e3a5f 0%, #334155 100%);
  border: none;
  font-weight: 600;
}

.auth-btn:hover {
  background: linear-gradient(135deg, #152a45 0%, #1e293b 100%);
}

.auth-footer {
  margin-top: 24px;
  text-align: center;
  font-size: 14px;
  color: #64748b;
}

.auth-link {
  color: #f59e0b;
  font-weight: 600;
  margin-left: 4px;
  text-decoration: none;
}

.auth-link:hover {
  color: #d97706;
}
</style>
