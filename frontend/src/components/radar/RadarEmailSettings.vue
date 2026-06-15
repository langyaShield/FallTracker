<script setup lang="ts">
/**
 * Radar · 邮箱配置 Tab
 *
 * 从 RadarPage.vue 拆出，独立维护 SMTP 配置的「拉取/保存/密码脱敏」逻辑。
 * 通过 v-model:loading 把内部 loading 状态暴露给父级用于 v-loading。
 */
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/lib/api'
import { extractErrorMessage } from '@/lib/error'

interface EmailSettings {
  smtp_server: string
  smtp_port: number
  smtp_username: string
  smtp_password: string
  email_from: string
}

defineProps<{ loading?: boolean }>()
const emit = defineEmits<{ (e: 'update:loading', v: boolean): void }>()

const emailSettings = ref<EmailSettings>({
  smtp_server: '',
  smtp_port: 587,
  smtp_username: '',
  smtp_password: '',
  email_from: '',
})
const emailSaving = ref(false)
const passwordMasked = ref(true)

const setLoading = (v: boolean) => emit('update:loading', v)

async function fetchEmailSettings() {
  setLoading(true)
  try {
    const res = await api.get('/settings/email')
    emailSettings.value = res.data
    passwordMasked.value = !!res.data.smtp_password && res.data.smtp_password.includes('*')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取邮箱配置失败'))
  } finally {
    setLoading(false)
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
    await api.put('/settings/email', payload)
    ElMessage.success('邮箱配置已保存')
    await fetchEmailSettings()
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '保存失败'))
  } finally {
    emailSaving.value = false
  }
}

onMounted(fetchEmailSettings)
defineExpose({ fetchEmailSettings })
</script>

<template>
  <el-card v-loading="loading" class="settings-card">
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
</template>

<style scoped>
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

.form-tip {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
}
</style>
