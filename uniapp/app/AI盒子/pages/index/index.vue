<template>
  <view class="page">
    <view class="hero-card">
      <view class="hero-top">
        <view>
          <text class="hero-eyebrow">AI BOX MOBILE</text>
          <text class="hero-title">AI盒子</text>
          <text class="hero-subtitle">模型对话 + 天气速览 + AIOT 控制入口</text>
        </view>
        <view class="hero-badge">{{ isSending ? '对话中' : '已连接' }}</view>
      </view>

      <view class="base-url-panel">
        <text class="panel-label">后端地址</text>
        <input
          class="base-url-input"
          v-model.trim="baseUrl"
          placeholder="例如：http://192.168.1.20:8888"
          @blur="persistBaseUrl"
        />
        <button class="mini-button" @click="persistBaseUrl">保存</button>
      </view>

      <view class="quick-row">
        <view class="quick-chip" @click="applyQuickPrompt('帮我总结今天的天气，并给一条穿衣建议')">天气建议</view>
        <view class="quick-chip" @click="applyQuickPrompt('查看当前在线设备状态')">设备状态</view>
        <view class="quick-chip" @click="applyQuickPrompt('帮我写一段简短日报')">日报草稿</view>
      </view>
    </view>

    <view class="weather-card">
      <view class="section-head">
        <view>
          <text class="section-title">天气接口</text>
          <text class="section-caption">兼容 wttr.in/{city}?format=j1</text>
        </view>
        <button class="ghost-button" @click="loadWeather" :disabled="weatherLoading">
          {{ weatherLoading ? '加载中' : '刷新' }}
        </button>
      </view>

      <view class="weather-search">
        <input class="city-input" v-model.trim="weatherCity" placeholder="输入城市，例如 chengdu / 成都" />
        <button class="primary-button small" @click="loadWeather" :disabled="weatherLoading">查询</button>
      </view>

      <view v-if="weatherError" class="error-banner">{{ weatherError }}</view>

      <view v-if="weatherSummary" class="weather-grid">
        <view class="weather-main">
          <text class="weather-city">{{ weatherSummary.city }}</text>
          <text class="weather-temp">{{ weatherSummary.temp }}°C</text>
          <text class="weather-desc">{{ weatherSummary.desc }}</text>
        </view>
        <view class="weather-side">
          <view class="metric-card">
            <text class="metric-label">体感</text>
            <text class="metric-value">{{ weatherSummary.feelsLike }}°C</text>
          </view>
          <view class="metric-card">
            <text class="metric-label">湿度</text>
            <text class="metric-value">{{ weatherSummary.humidity }}%</text>
          </view>
          <view class="metric-card wide">
            <text class="metric-label">接口地址</text>
            <text class="metric-url">{{ weatherUrlPreview }}</text>
          </view>
        </view>
      </view>
    </view>

    <view class="chat-card">
      <view class="section-head">
        <view>
          <text class="section-title">AI 对话</text>
          <text class="section-caption">默认调用后端当前默认模型</text>
        </view>
        <button class="ghost-button" @click="clearMessages">清空</button>
      </view>

      <scroll-view class="message-list" scroll-y :scroll-top="scrollTop">
        <view v-for="item in messages" :key="item.id" class="message-row" :class="{ user: item.role === 'user' }">
          <view class="message-bubble">
            <text class="message-role">{{ item.role === 'user' ? '我' : 'AI' }}</text>
            <text class="message-text">{{ item.displayText }}</text>
            <text v-if="item.meta" class="message-meta">{{ item.meta }}</text>
          </view>
        </view>
        <view v-if="messages.length === 0" class="empty-state">
          <text class="empty-title">从一个问题开始</text>
          <text class="empty-copy">你可以问天气、设备状态，或者直接和默认模型对话。</text>
        </view>
      </scroll-view>

      <view v-if="chatError" class="error-banner">{{ chatError }}</view>

      <view class="composer-card">
        <textarea
          class="composer-input"
          v-model="draft"
          maxlength="-1"
          auto-height
          placeholder="输入问题，例如：帮我查询成都天气并总结一下"
        />
        <view class="composer-actions">
          <button class="ghost-button" @click="toggleVoiceInput">
            {{ recording ? '停止录音' : '语音输入' }}
          </button>
          <button class="ghost-button" @click="notifyTtsPending">语音播报</button>
          <button class="primary-button" @click="sendMessage" :disabled="isSending">发送</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
const STORAGE_KEY = 'agent-mobile-base-url'

export default {
  data() {
    return {
      baseUrl: 'http://127.0.0.1:8888',
      weatherCity: 'chengdu',
      weatherLoading: false,
      weatherError: '',
      weatherSummary: null,
      weatherUrlPreview: '',
      draft: '',
      isSending: false,
      chatError: '',
      messages: [],
      scrollTop: 0,
      nextMessageId: 1,
      recorderManager: null,
      recording: false,
      recordStartAt: 0
    }
  },
  onLoad() {
    const savedBaseUrl = uni.getStorageSync(STORAGE_KEY)
    if (savedBaseUrl) {
      this.baseUrl = savedBaseUrl
    }
    if (typeof uni.getRecorderManager === 'function') {
      this.recorderManager = uni.getRecorderManager()
      this.recorderManager.onStop(this.handleRecordStop)
      this.recorderManager.onError(() => {
        this.recording = false
        uni.showToast({ title: '录音失败', icon: 'none' })
      })
    }
    this.pushMessage('assistant', '你好，我已经准备好了。你可以先查天气，也可以直接开始聊天。', '默认模型')
    this.loadWeather()
  },
  computed: {
    normalizedBaseUrl() {
      return (this.baseUrl || '').trim().replace(/\/$/, '')
    }
  },
  methods: {
    request(options) {
      return new Promise((resolve, reject) => {
        uni.request({
          ...options,
          success: resolve,
          fail: reject
        })
      })
    },
    persistBaseUrl() {
      if (!this.normalizedBaseUrl) {
        uni.showToast({ title: '请填写后端地址', icon: 'none' })
        return
      }
      uni.setStorageSync(STORAGE_KEY, this.normalizedBaseUrl)
      this.baseUrl = this.normalizedBaseUrl
      uni.showToast({ title: '已保存', icon: 'success' })
    },
    applyQuickPrompt(text) {
      this.draft = text
    },
    async loadWeather() {
      if (!this.normalizedBaseUrl) {
        this.weatherError = '请先配置后端地址'
        return
      }
      this.weatherLoading = true
      this.weatherError = ''
      const city = this.weatherCity || 'chengdu'
      const url = `${this.normalizedBaseUrl}/mobile/weather?city=${encodeURIComponent(city)}`
      this.weatherUrlPreview = url
      try {
        const response = await this.request({
          url,
          method: 'GET',
          timeout: 25000
        })
        const body = response.data || {}
        const current = (body.data && body.data.current_condition && body.data.current_condition[0]) || {}
        this.weatherSummary = {
          city: body.city || city,
          temp: current.temp_C || '--',
          feelsLike: current.FeelsLikeC || '--',
          humidity: current.humidity || '--',
          desc: (((current.lang_zh && current.lang_zh[0]) || {}).value) || (((current.weatherDesc && current.weatherDesc[0]) || {}).value) || '暂无描述'
        }
      } catch (error) {
        this.weatherSummary = null
        this.weatherError = `天气查询失败：${(error && error.errMsg) || error.message || error}`
      } finally {
        this.weatherLoading = false
      }
    },
    clearMessages() {
      this.messages = []
      this.chatError = ''
      this.pushMessage('assistant', '会话已清空，我们可以重新开始。', '系统提示')
    },
    pushMessage(role, text, meta = '') {
      this.messages.push({
        id: this.nextMessageId++,
        role,
        text,
        displayText: text,
        meta
      })
      this.bumpScroll()
      return this.messages[this.messages.length - 1]
    },
    bumpScroll() {
      this.$nextTick(() => {
        this.scrollTop = this.messages.length * 1000
      })
    },
    async sendMessage() {
      const message = (this.draft || '').trim()
      if (!message || this.isSending) {
        return
      }
      if (!this.normalizedBaseUrl) {
        this.chatError = '请先配置后端地址'
        return
      }
      this.chatError = ''
      this.isSending = true
      this.pushMessage('user', message)
      this.draft = ''
      const assistantMessage = this.pushMessage('assistant', '', '模型思考中')

      try {
        const response = await this.request({
          url: `${this.normalizedBaseUrl}/mobile/chat`,
          method: 'POST',
          header: {
            'Content-Type': 'application/json'
          },
          data: { message },
          timeout: 90000
        })
        const body = response.data || {}
        if (body.error) {
          throw new Error(body.error)
        }
        assistantMessage.meta = body.model ? `模型：${body.model}` : '默认模型'
        await this.animateAssistantReply(assistantMessage, body.reply || '模型没有返回内容')
      } catch (error) {
        assistantMessage.displayText = '请求失败，请检查后端地址或服务状态。'
        assistantMessage.meta = '连接异常'
        this.chatError = `发送失败：${(error && error.errMsg) || error.message || error}`
      } finally {
        this.isSending = false
      }
    },
    async animateAssistantReply(message, finalText) {
      message.text = finalText
      message.displayText = ''
      const chars = Array.from(finalText)
      for (let index = 0; index < chars.length; index += 1) {
        message.displayText += chars[index]
        this.bumpScroll()
        await new Promise((resolve) => setTimeout(resolve, index < 24 ? 18 : 10))
      }
    },
    toggleVoiceInput() {
      if (!this.recorderManager) {
        uni.showToast({ title: '当前平台不支持录音', icon: 'none' })
        return
      }
      if (this.recording) {
        this.recorderManager.stop()
        return
      }
      this.recording = true
      this.recordStartAt = Date.now()
      this.recorderManager.start({
        duration: 60000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 96000,
        format: 'mp3'
      })
      uni.showToast({ title: '开始录音', icon: 'none' })
    },
    handleRecordStop() {
      const seconds = Math.max(1, Math.round((Date.now() - this.recordStartAt) / 1000))
      this.recording = false
      this.draft = `${this.draft ? `${this.draft} ` : ''}[语音 ${seconds}s：请在此补充识别文本]`
      uni.showToast({ title: '录音完成', icon: 'success' })
    },
    notifyTtsPending() {
      uni.showToast({ title: 'TTS 将在后端接入后启用', icon: 'none' })
    }
  }
}
</script>

<style>
.page {
  min-height: 100vh;
  padding: 28rpx 24rpx 40rpx;
  background:
    radial-gradient(circle at top left, rgba(255, 196, 107, 0.28), transparent 34%),
    radial-gradient(circle at bottom right, rgba(90, 132, 255, 0.18), transparent 28%),
    #f4efe6;
  box-sizing: border-box;
}

.hero-card,
.weather-card,
.chat-card {
  background: rgba(255, 251, 245, 0.92);
  border: 1rpx solid rgba(42, 52, 65, 0.08);
  border-radius: 28rpx;
  padding: 28rpx;
  box-shadow: 0 18rpx 44rpx rgba(34, 28, 22, 0.08);
  backdrop-filter: blur(12rpx);
}

.weather-card,
.chat-card {
  margin-top: 22rpx;
}

.hero-top,
.section-head,
.weather-search,
.composer-actions,
.quick-row,
.base-url-panel {
  display: flex;
}

.hero-top,
.section-head {
  justify-content: space-between;
  align-items: flex-start;
}

.hero-eyebrow {
  display: block;
  color: #8f6b3c;
  font-size: 20rpx;
  letter-spacing: 4rpx;
  margin-bottom: 10rpx;
}

.hero-title,
.section-title,
.weather-city,
.weather-temp,
.empty-title {
  display: block;
}

.hero-title {
  font-size: 56rpx;
  color: #1f2732;
  font-weight: 700;
}

.hero-subtitle,
.section-caption,
.metric-label,
.message-meta,
.empty-copy,
.panel-label {
  color: #66707d;
  font-size: 24rpx;
}

.hero-subtitle {
  margin-top: 10rpx;
}

.hero-badge {
  background: #1f2732;
  color: #f8f3eb;
  padding: 12rpx 18rpx;
  border-radius: 999rpx;
  font-size: 22rpx;
}

.base-url-panel {
  align-items: center;
  gap: 14rpx;
  margin-top: 24rpx;
}

.panel-label {
  width: 110rpx;
  flex-shrink: 0;
}

.base-url-input,
.city-input,
.composer-input {
  flex: 1;
  background: #fffdf9;
  border: 1rpx solid rgba(31, 39, 50, 0.12);
  border-radius: 20rpx;
  padding: 18rpx 20rpx;
  color: #1f2732;
  font-size: 28rpx;
  box-sizing: border-box;
}

.base-url-input,
.city-input {
  min-height: 84rpx;
}

.base-url-input .uni-input-wrapper,
.city-input .uni-input-wrapper {
  display: flex;
  align-items: center;
  min-height: 48rpx;
}

.base-url-input .uni-input-input,
.city-input .uni-input-input {
  height: 48rpx;
  line-height: 48rpx;
  font-size: 28rpx;
  color: #1f2732;
}

.base-url-input .uni-input-placeholder,
.city-input .uni-input-placeholder {
  line-height: 48rpx;
  font-size: 28rpx;
}

.quick-row {
  flex-wrap: wrap;
  gap: 14rpx;
  margin-top: 22rpx;
}

.quick-chip {
  padding: 14rpx 18rpx;
  border-radius: 18rpx;
  background: #ebe3d4;
  color: #43362a;
  font-size: 24rpx;
}

.section-title {
  font-size: 34rpx;
  color: #1f2732;
  font-weight: 700;
}

.weather-search {
  gap: 14rpx;
  margin-top: 24rpx;
}

.weather-grid {
  margin-top: 22rpx;
}

.weather-main {
  padding: 26rpx;
  border-radius: 24rpx;
  background: linear-gradient(135deg, #1f2732, #314156);
}

.weather-city {
  color: #ffefc5;
  font-size: 30rpx;
}

.weather-temp {
  color: #ffffff;
  font-size: 76rpx;
  line-height: 1.1;
  margin-top: 8rpx;
}

.weather-desc {
  color: #dae4f2;
  font-size: 26rpx;
  margin-top: 10rpx;
}

.weather-side {
  display: flex;
  flex-wrap: wrap;
  gap: 14rpx;
  margin-top: 16rpx;
}

.metric-card {
  width: calc(50% - 7rpx);
  background: #f7f0e3;
  border-radius: 22rpx;
  padding: 20rpx;
  box-sizing: border-box;
}

.metric-card.wide {
  width: 100%;
}

.metric-value {
  display: block;
  margin-top: 8rpx;
  color: #1f2732;
  font-size: 32rpx;
  font-weight: 700;
}

.metric-url {
  display: block;
  margin-top: 8rpx;
  color: #5d6670;
  font-size: 22rpx;
  line-height: 1.5;
}

.message-list {
  height: 720rpx;
  margin-top: 22rpx;
}

.message-row {
  display: flex;
  margin-bottom: 18rpx;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 88%;
  padding: 22rpx;
  border-radius: 24rpx;
  background: #fffaf2;
  border: 1rpx solid rgba(31, 39, 50, 0.08);
}

.message-row.user .message-bubble {
  background: linear-gradient(135deg, #1f2732, #324257);
}

.message-role,
.message-text,
.message-meta {
  display: block;
}

.message-role {
  font-size: 22rpx;
  color: #8d6c41;
  margin-bottom: 10rpx;
}

.message-text {
  color: #1f2732;
  font-size: 28rpx;
  line-height: 1.7;
}

.message-row.user .message-role,
.message-row.user .message-text,
.message-row.user .message-meta {
  color: #f7f1e8;
}

.empty-state {
  padding: 90rpx 40rpx;
  text-align: center;
}

.empty-copy {
  display: block;
  margin-top: 12rpx;
}

.composer-card {
  margin-top: 18rpx;
  padding: 20rpx;
  border-radius: 24rpx;
  background: #f8f1e6;
}

.composer-input {
  min-height: 150rpx;
}

.composer-actions {
  justify-content: flex-end;
  gap: 14rpx;
  margin-top: 16rpx;
}

.primary-button,
.ghost-button,
.mini-button {
  border: none;
  border-radius: 18rpx;
  font-size: 24rpx;
}

.primary-button {
  background: #1f2732;
  color: #fff8ef;
  padding: 0 26rpx;
}

.primary-button.small {
  height: 84rpx;
  line-height: 84rpx;
}

.ghost-button,
.mini-button {
  background: #e7dece;
  color: #2c3540;
}

.ghost-button {
  padding: 0 24rpx;
}

.mini-button {
  width: 110rpx;
  font-size: 22rpx;
}

.error-banner {
  margin-top: 16rpx;
  padding: 18rpx 20rpx;
  border-radius: 18rpx;
  background: rgba(186, 68, 46, 0.12);
  color: #9c3b26;
  font-size: 24rpx;
}
</style>
