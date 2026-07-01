<script setup lang="ts">
/**
 * Radar · 通知设置 Tab
 *
 * 优化点：
 * - 常见邮箱一键预设（QQ/163/Gmail/Outlook），自动填充服务器和端口
 * - 通俗化表单标签和提示
 * - 密码脱敏处理
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

// 常见邮箱预设
const EMAIL_PRESETS = [
  { label: 'QQ邮箱', server: 'smtp.qq.com', port: 587, hint: '需在 QQ邮箱设置 → 账户 中开启 SMTP 并获取授权码' },
  { label: '163邮箱', server: 'smtp.163.com', port: 465, hint: '需在 163邮箱设置 中开启 SMTP 并获取授权码' },
  { label: 'Gmail', server: 'smtp.gmail.com', port: 587, hint: '需开启两步验证后生成应用专用密码' },
  { label: 'Outlook', server: 'smtp.office365.com', port: 587, hint: '直接使用登录密码即可' },
]

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
const emailTesting = ref(false)
const passwordMasked = ref(true)
const selectedPreset = ref('')

const setLoading = (v: boolean) => emit('update:loading', v)

async function fetchEmailSettings() {
  setLoading(true)
  try {
    const res = await api.get('/settings/email')
    emailSettings.value = res.data
    passwordMasked.value = !!res.data.smtp_password && res.data.smtp_password.includes('*')
    // 匹配已有配置到预设
    const server = res.data.smtp_server || ''
    const matched = EMAIL_PRESETS.find(p => p.server === server)
    selectedPreset.value = matched ? matched.label : ''
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '获取邮箱配置失败'))
  } finally {
    setLoading(false)
  }
}

function onPresetChange(label: string) {
  const preset = EMAIL_PRESETS.find(p => p.label === label)
  if (preset) {
    emailSettings.value.smtp_server = preset.server
    emailSettings.value.smtp_port = preset.port
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

async function testEmailSettings() {
  emailTesting.value = true
  try {
    const res = await api.post('/settings/email/test')
    ElMessage.success(res.data.message || '测试邮件发送成功')
  } catch (e: any) {
    ElMessage.error(extractErrorMessage(e, '测试邮件发送失败'))
  } finally {
    emailTesting.value = false
  }
}

const currentHint = () => {
  const preset = EMAIL_PRESETS.find(p => p.label === selectedPreset.value)
  return preset?.hint || ''
}

onMounted(fetchEmailSettings)
defineExpose({ fetchEmailSettings })
</script>

<template>
  <el-card v-loading="loading" class="settings-card">
    <template #header>
      <span class="card-title">通知邮箱设置</span>
    </template>
    <p class="card-desc">配置邮箱后，当监控匹配到目标时可以自动发邮件通知你。</p>

    <el-form :model="emailSettings" label-width="120px" style="max-width: 520px; margin-top: 20px">
      <!-- 邮箱类型快捷选择 -->
      <el-form-item label="邮箱类型">
        <el-radio-group v-model="selectedPreset" @change="onPresetChange">
          <el-radio-button v-for="p in EMAIL_PRESETS" :key="p.label" :value="p.label">
            {{ p.label }}
          </el-radio-button>
        </el-radio-group>
        <div v-if="currentHint()" class="preset-hint">{{ currentHint() }}</div>
      </el-form-item>

      <el-form-item label="邮箱服务器">
        <el-input v-model="emailSettings.smtp_server" placeholder="smtp.qq.com" />
        <div class="form-tip">选择邮箱类型后自动填充，也可手动输入</div>
      </el-form-item>
      <el-form-item label="端口号">
        <el-input-number v-model="emailSettings.smtp_port" :min="1" :max="65535" />
      </el-form-item>
      <el-form-item label="邮箱账号">
        <el-input v-model="emailSettings.smtp_username" placeholder="your@email.com" />
      </el-form-item>
      <el-form-item label="授权码/密码">
        <el-input
          v-model="emailSettings.smtp_password"
          type="password"
          show-password
          placeholder="输入授权码或密码"
          @input="onPasswordInput"
        />
        <div class="form-tip">大多数邮箱需要使用「授权码」而非登录密码，请在邮箱设置中获取</div>
      </el-form-item>
      <el-form-item label="发件人邮箱">
        <el-input v-model="emailSettings.email_from" placeholder="your@email.com" />
        <div class="form-tip">通常与邮箱账号相同</div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="emailSaving" @click="saveEmailSettings">
          保存配置
        </el-button>
        <el-button :loading="emailTesting" @click="testEmailSettings">
          一键测试
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

.preset-hint {
  margin-top: 8px;
  padding: 8px 12px;
  background: #fffbeb;
  border-radius: 6px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.5;
}

.form-tip {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-top: 4px;
  line-height: 1.4;
}
</style>
