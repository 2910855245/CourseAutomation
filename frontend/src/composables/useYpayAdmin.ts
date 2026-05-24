// YPay 管理：账户、配置、订单、通道测试、广告
import { ref, reactive, computed } from 'vue'
import { useAppStore } from '@/stores/app'
import { api } from '@/api'

export function useYpayAdmin() {
  const store = useAppStore()

  // ── YPay ──
  const ypayTab = ref<'settings' | 'orders' | 'qrcodes'>('settings')
  const ypayForm = reactive({ key: '', close_time: '5', pay_timeout: '300' })
  const ypaySaving = ref(false)
  const pairQrTs = ref(Date.now())
  const pairQrLoading = ref(true)
  const downloadQrLoading = ref(true)
  const pairQrImage = ref('')
  const downloadQrImage = ref('')
  const ypayLoaded = ref(false)
  const ypayStatus = ref<any>(null)
  const ypayTesting = ref(false)
  const ypayTestResult = ref<any>(null)
  const ypayOrders = ref<any[]>([])
  const ypayOrdersTotal = ref(0)
  const ypayOrdersPage = ref(1)
  const ypayOrderStatusFilter = ref<number | null>(null)
  const ypayOrderFilters = [
    { label: '全部', value: null },
    { label: '未支付', value: 0 },
    { label: '已支付', value: 1 },
    { label: '已关闭', value: -1 },
  ]
  const loadingYpayOrders = ref(false)
  const ypayAccounts = ref<any[]>([])
  const loadingAccounts = ref(false)
  const showAccountModal = ref(false)
  const editingAccount = ref<any>(null)
  const accountForm = reactive({
    type: 'wxpay', code: 'wxpay_software', name: '', qr_url: '', zfb_pid: '',
    alipay_appid: '', alipay_public_key: '', alipay_private_key: '',
    app_public_cert: '', alipay_public_cert: '', alipay_root_cert: '',
    cookie: '', wx_guid: '', qq: '', cloud_id: '', qr_type: '', memo: '', remark: '', channel_mode: 1,
  })
  const savingAccount = ref(false)
  const showCertFields = ref(false)
  const showChannelTest = ref(false)
  const channelTestAccount = ref<any>(null)
  const channelTestLoading = ref(false)
  const channelTestChecks = ref<any[]>([])
  const channelTestQrImage = ref('')
  const channelTestAllOk = ref(false)
  const qrUploading = ref(false)
  const qrFileInput = ref<HTMLInputElement | null>(null)

  const payTypeLabels: Record<number, string> = { 1: '微信', 2: '支付宝' }
  const ypayStateLabels: Record<string, string> = { '0': '未支付', '1': '已支付', '-1': '已关闭' }
  const typeLabels: Record<string, string> = { wxpay: '微信', alipay: '支付宝' }
  const defaultCodes: Record<string, string> = { wxpay: 'wxpay_dy', alipay: 'alipay_dmf' }
  const wxAccounts = computed(() => ypayAccounts.value.filter(a => a.type === 'wxpay'))
  const aliAccounts = computed(() => ypayAccounts.value.filter(a => a.type === 'alipay'))

  const channelCodeLabels: Record<string, string> = {
    wxpay_dy: '微信店员版', wxpay_software: '微信软件版',
    wxpay_skd: '微信收款单', wxpay_cloudzs: '微信赞赏码',
    alipay_dmf: '支付宝当面付', alipay_official: '支付宝官方支付',
    dougong_wxpay: '汇付斗拱-微信', dougong_alipay: '汇付斗拱-支付宝',
    lkl_wxpay: '拉卡拉-微信', lkl_alipay: '拉卡拉-支付宝',
    lebrush_wxpay: '乐刷-微信', lebrush_alipay: '乐刷-支付宝',
  }
  const channelCodeHelp: Record<string, { desc: string; how: string; need: string; tip: string }> = {
    wxpay_dy: { desc: '免挂方案，不需要装软件', how: '在你的微信收款商业版里添加一个"店员"', need: '一个额外的微信号当店员 + Cookie', tip: '最简单的方案' },
    wxpay_software: { desc: '需要一台备用手机挂着监控 APP', how: '在备用手机上安装收款监控 APP', need: '一台安卓手机 + 安装APP', tip: '手机不能关屏杀后台' },
    wxpay_skd: { desc: '生成微信收款单链接', how: '系统生成收款单链接', need: '收款单相关配置', tip: '用户体验好' },
    wxpay_cloudzs: { desc: '使用微信赞赏码收款', how: '上传赞赏码图片', need: '微信赞赏码图片', tip: '适合金额不固定' },
    alipay_dmf: { desc: '支付宝官方当面付接口', how: '在支付宝开放平台创建应用', need: 'APPID + 应用私钥 + 支付宝公钥', tip: '需要企业资质' },
    alipay_official: { desc: '支付宝官方 PC/WAP 支付接口', how: '在支付宝开放平台创建应用', need: 'APPID + 密钥', tip: '支持PC和手机' },
    dougong_wxpay: { desc: '通过汇付斗拱平台聚合收款（微信）', how: '在斗拱平台注册商户', need: '商户号 + 密钥', tip: '第三方聚合' },
    dougong_alipay: { desc: '通过汇付斗拱平台聚合收款（支付宝）', how: '同上', need: '商户号 + 密钥', tip: '同上' },
    lkl_wxpay: { desc: '通过拉卡拉平台聚合收款（微信）', how: '在拉卡拉注册商户', need: '商户号 + 密钥', tip: '老牌平台' },
    lkl_alipay: { desc: '通过拉卡拉平台聚合收款（支付宝）', how: '同上', need: '商户号 + 密钥', tip: '同上' },
    lebrush_wxpay: { desc: '通过乐刷平台聚合收款（微信）', how: '在乐刷注册商户', need: '商户号 + 密钥', tip: '第三方聚合' },
    lebrush_alipay: { desc: '通过乐刷平台聚合收款（支付宝）', how: '同上', need: '商户号 + 密钥', tip: '同上' },
  }

  function codeLabel(code: string) { return channelCodeLabels[code] || code }

  function fmtHeartbeat(secondsAgo: number, fallback: string): string {
    if (secondsAgo < 0) return fallback ? fallback.replace('T', ' ').substring(0, 19) : '无记录'
    if (secondsAgo < 60) return `${secondsAgo} 秒前`
    if (secondsAgo < 3600) return `${Math.floor(secondsAgo / 60)} 分钟前`
    if (secondsAgo < 86400) return `${Math.floor(secondsAgo / 3600)} 小时前`
    return `${Math.floor(secondsAgo / 86400)} 天前`
  }

  function genRandomStr(len: number): string {
    const chars = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789'
    let r = ''
    for (let i = 0; i < len; i++) r += chars.charAt(Math.floor(Math.random() * chars.length))
    return r
  }

  function triggerQrUpload() { qrFileInput.value?.click() }

  async function onQrFileChange(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    qrUploading.value = true
    try {
      const r = await api.ypay.decodeQr(file)
      if (r.code === 0 && r.data) {
        accountForm.qr_url = r.data
        store.toast('二维码解码成功', 'success')
      } else {
        store.toast(r.message || '解码失败', 'error')
      }
    } catch { store.toast('上传失败', 'error') }
    finally {
      qrUploading.value = false
      if (qrFileInput.value) qrFileInput.value.value = ''
    }
  }

  function resetAccountForm() {
    accountForm.name = ''; accountForm.qr_url = ''; accountForm.zfb_pid = ''
    accountForm.alipay_appid = ''; accountForm.alipay_public_key = ''; accountForm.alipay_private_key = ''
    accountForm.app_public_cert = ''; accountForm.alipay_public_cert = ''; accountForm.alipay_root_cert = ''
    accountForm.cookie = ''; accountForm.wx_guid = ''; accountForm.qq = ''
    accountForm.cloud_id = ''; accountForm.qr_type = ''; accountForm.memo = ''
    accountForm.remark = ''; accountForm.channel_mode = 1
  }

  function openAddAccount(type: string) {
    editingAccount.value = null; accountForm.type = type
    accountForm.code = defaultCodes[type] || ''
    resetAccountForm(); showAccountModal.value = true
  }

  function openEditAccount(acc: any) {
    editingAccount.value = acc
    accountForm.type = acc.type; accountForm.code = acc.code; accountForm.name = acc.name
    accountForm.qr_url = acc.qr_url || ''; accountForm.zfb_pid = acc.zfb_pid || ''
    accountForm.alipay_appid = acc.alipay_appid || ''; accountForm.alipay_public_key = acc.alipay_public_key || ''
    accountForm.alipay_private_key = acc.alipay_private_key || ''; accountForm.app_public_cert = acc.app_public_cert || ''
    accountForm.alipay_public_cert = acc.alipay_public_cert || ''; accountForm.alipay_root_cert = acc.alipay_root_cert || ''
    accountForm.cookie = acc.cookie || ''; accountForm.wx_guid = acc.wx_guid || ''
    accountForm.qq = acc.qq || ''; accountForm.cloud_id = acc.cloud_id || ''
    accountForm.qr_type = acc.qr_type || ''; accountForm.memo = acc.memo || ''
    accountForm.remark = acc.remark || ''; accountForm.channel_mode = acc.channel_mode || 1
    if (acc.app_public_cert || acc.alipay_public_cert || acc.alipay_root_cert) showCertFields.value = true
    showAccountModal.value = true
  }

  function closeAccountModal() {
    showAccountModal.value = false; editingAccount.value = null; showCertFields.value = false
  }

  async function loadAccounts() {
    loadingAccounts.value = true
    try {
      const r = await api.ypay.accounts.list()
      if (r.success) ypayAccounts.value = r.data || []
    } catch { /* */ }
    finally { loadingAccounts.value = false }
  }

  async function saveAccount() {
    if (!accountForm.name.trim()) { store.toast('请输入通道名称', 'warning'); return }
    const needQrUrl = accountForm.type === 'wxpay' || ['dougong_alipay','lebrush_alipay'].includes(accountForm.code)
    const needAppid = ['alipay_dmf','alipay_official'].includes(accountForm.code)
    const needRemark = accountForm.code.startsWith('lkl_')
    if (needQrUrl && !accountForm.qr_url.trim()) { store.toast('请输入收款码内容', 'warning'); return }
    if (needAppid && !accountForm.alipay_appid.trim()) { store.toast('请输入应用APPID', 'warning'); return }
    if (needRemark && !accountForm.remark.trim()) { store.toast('请输入Authorization令牌', 'warning'); return }
    savingAccount.value = true
    try {
      const r = editingAccount.value
        ? await api.ypay.accounts.update(editingAccount.value.id, accountForm)
        : await api.ypay.accounts.create(accountForm)
      if (r.success) {
        store.toast(editingAccount.value ? '通道已更新' : '通道已添加', 'success')
        closeAccountModal(); loadAccounts()
      } else {
        store.toast(r.message || '操作失败', 'error')
      }
    } catch { store.toast('操作失败', 'error') }
    finally { savingAccount.value = false }
  }

  async function deleteAccount(acc: any) {
    if (!confirm(`确定删除通道「${acc.name}」？`)) return
    try {
      const r = await api.ypay.accounts.delete(acc.id)
      if (r.success) { store.toast('已删除', 'success'); loadAccounts() }
      else store.toast(r.message || '删除失败', 'error')
    } catch { store.toast('删除失败', 'error') }
  }

  async function toggleAccount(acc: any) {
    const newStatus = acc.is_status === 1 ? 0 : 1
    try {
      const r = await api.ypay.accounts.update(acc.id, { is_status: newStatus })
      if (r.success) { acc.is_status = newStatus; store.toast(newStatus ? '已启用' : '已停用', 'success') }
      else store.toast(r.message || '操作失败', 'error')
    } catch { store.toast('操作失败', 'error') }
  }

  async function testChannel(acc: any) {
    if (!acc) return
    channelTestAccount.value = acc; showChannelTest.value = true
    channelTestLoading.value = true; channelTestChecks.value = []
    channelTestQrImage.value = ''; channelTestAllOk.value = false
    try {
      const r = await api.ypay.channelTest(acc.id)
      if (r.success && r.data) {
        channelTestChecks.value = r.data.checks || []
        channelTestAllOk.value = r.data.all_ok || false
        channelTestQrImage.value = r.data.qr_image || ''
      } else {
        channelTestChecks.value = [{ name: '请求', ok: false, msg: r.message || '测试失败' }]
      }
    } catch {
      channelTestChecks.value = [{ name: '网络', ok: false, msg: '无法连接服务器' }]
    } finally { channelTestLoading.value = false }
  }

  async function loadYpay() {
    try {
      const [cfgRes, statusRes] = await Promise.all([
        api.ypay.config.get(),
        api.ypay.status(),
      ])
      const cfg = cfgRes.data || {}
      ypayForm.key = cfg.key || ''
      if (!ypayForm.key && !cfg.key_set) { ypayForm.key = genRandomStr(16); await saveYpayKeyOnly() }
      ypayForm.close_time = cfg.close_time || cfg.closeTime || '5'
      ypayForm.pay_timeout = cfg.pay_timeout || cfg.payTimeout || '300'
      ypayStatus.value = statusRes.data || null
      ypayLoaded.value = true
    } catch { /* */ }
    loadYpayOrders(); loadAccounts(); loadPairQr()
  }

  async function saveYpaySettings() {
    ypaySaving.value = true
    try {
      const body: any = { key: ypayForm.key, close_time: ypayForm.close_time, pay_timeout: ypayForm.pay_timeout }
      const r = await api.ypay.config.save(body)
      if (r.success) store.toast('支付配置已保存', 'success')
      else store.toast(r.message || '保存失败', 'error')
    } catch { store.toast('保存失败', 'error') }
    finally { ypaySaving.value = false }
  }

  async function saveYpayKeyOnly() {
    await api.ypay.config.save({ key: ypayForm.key })
  }

  async function regenerateYpayKey() {
    ypayForm.key = genRandomStr(16)
    await saveYpayKeyOnly()
    pairQrLoading.value = true; downloadQrLoading.value = true
    pairQrTs.value = Date.now(); loadPairQr()
    store.toast('通讯密钥已重新生成', 'success')
  }

  async function loadPairQr() {
    pairQrLoading.value = true; downloadQrLoading.value = true
    try {
      const [pairRes, dlRes] = await Promise.all([
        api.ypay.appQrcode().catch(() => null),
        fetch('/api/app/download-qr', { headers: { 'Accept': 'application/json' } }).then(r => r.json()).catch(() => null),
      ])
      if (pairRes?.data?.qr_image) pairQrImage.value = pairRes.data.qr_image
      if (dlRes?.data?.qr_image) downloadQrImage.value = dlRes.data.qr_image
    } catch { /* */ }
    pairQrLoading.value = false; downloadQrLoading.value = false
  }

  async function loadYpayOrders() {
    loadingYpayOrders.value = true
    try {
      const params: any = { page: ypayOrdersPage.value, limit: 20 }
      if (ypayOrderStatusFilter.value !== null) params.status = ypayOrderStatusFilter.value
      const r = await api.ypay.orders.list(params)
      if (r.success && r.data) {
        ypayOrders.value = r.data.items || []
        ypayOrdersTotal.value = r.data.total || 0
      }
    } catch { /* */ }
    finally { loadingYpayOrders.value = false }
  }

  async function closeExpiredYpayOrders() {
    try {
      const r = await api.ypay.closeExpired()
      store.toast(r.message || '操作完成', 'success')
      loadYpayOrders(); loadYpay()
    } catch (e: any) { store.toast(e.message || '操作失败', 'error') }
  }

  async function clearYpayOrderHistory() {
    try { const res = await api.ypay.clearOrders(); loadYpayOrders(); store.toast(res.message || '支付订单已清除', 'success') }
    catch (e: any) { store.toast(e.message, 'error') }
  }

  async function runYpayTest() {
    ypayTesting.value = true; ypayTestResult.value = null
    try {
      const r = await api.ypay.diagnose()
      ypayTestResult.value = r.data || { all_ok: false, checks: [], summary: '测试请求失败' }
    } catch {
      ypayTestResult.value = { all_ok: false, checks: [{ name: '网络', ok: false, msg: '无法连接服务器' }], summary: '无法连接到服务器' }
    }
    finally { ypayTesting.value = false }
  }

  async function resetYpayConnection() {
    try {
      const r = await api.ypay.resetConnection()
      alert(r.message || '已重置'); await loadYpay()
    } catch { alert('重置失败，请检查网络') }
  }

  // ── Ads ──
  const adsList = ref<any[]>([])
  const loadingAds = ref(false)
  const showAdModal = ref(false)
  const editingAd = ref<any>(null)
  const adForm = reactive({ slot: 1, name: '', html_content: '' })
  const savingAd = ref(false)
  const adFileInput = ref<HTMLInputElement | null>(null)
  const adImgInput = ref<HTMLInputElement | null>(null)
  const adFileUploading = ref(false)

  async function loadAds() {
    loadingAds.value = true
    try { const r = await api.adminAds.list(); adsList.value = r.data || [] }
    catch { adsList.value = [] }
    finally { loadingAds.value = false }
  }

  function openCreateAd() {
    editingAd.value = null
    const usedSlots = adsList.value.map(a => a.slot)
    let nextSlot = 1
    for (let i = 1; i <= 5; i++) { if (!usedSlots.includes(i)) { nextSlot = i; break } }
    adForm.slot = nextSlot; adForm.name = ''; adForm.html_content = ''
    showAdModal.value = true
  }

  function openEditAd(ad: any) {
    editingAd.value = ad; adForm.slot = ad.slot; adForm.name = ad.name
    adForm.html_content = ad.html_content; showAdModal.value = true
  }

  async function saveAd() {
    if (!adForm.name.trim()) { store.toast('请输入广告名称', 'warning'); return }
    savingAd.value = true
    try {
      if (editingAd.value) {
        await api.adminAds.update(editingAd.value.id, { name: adForm.name, html_content: adForm.html_content })
        store.toast('更新成功', 'success')
      } else {
        await api.adminAds.create({ slot: adForm.slot, name: adForm.name, html_content: adForm.html_content })
        store.toast('添加成功', 'success')
      }
      showAdModal.value = false; await loadAds()
    } catch (e: any) { store.toast(e.message || '操作失败', 'error') }
    finally { savingAd.value = false }
  }

  async function toggleAdActive(ad: any) {
    await api.adminAds.update(ad.id, { is_active: ad.is_active ? 0 : 1 }); await loadAds()
  }

  async function deleteAd(ad: any) {
    if (!confirm(`确定删除广告"${ad.name}"？`)) return
    await api.adminAds.delete(ad.id); store.toast('已删除', 'success'); await loadAds()
  }

  function triggerAdFileUpload() { adFileInput.value?.click() }
  function triggerAdImgUpload() { adImgInput.value?.click() }

  function onAdFileChange(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    if (!file.name.endsWith('.html') && !file.name.endsWith('.htm') && file.type !== 'text/html') {
      store.toast('请上传 HTML 文件', 'warning'); return
    }
    adFileUploading.value = true
    const reader = new FileReader()
    reader.onload = () => {
      let html = reader.result as string
      const relImgs = html.match(/<img[^>]+src=["'](?!https?:\/\/|data:)[^"']+["']/gi)
      if (relImgs && relImgs.length > 0) {
        store.toast(`HTML 中有 ${relImgs.length} 个本地图片引用，建议用「插入图片」按钮替换`, 'warning')
      }
      adForm.html_content = html
      if (!adForm.name.trim()) adForm.name = file.name.replace(/\.html?$/i, '')
      adFileUploading.value = false; store.toast('文件已读取', 'success')
    }
    reader.onerror = () => { adFileUploading.value = false; store.toast('文件读取失败', 'error') }
    reader.readAsText(file); (e.target as HTMLInputElement).value = ''
  }

  function onAdImgChange(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) { store.toast('请选择图片文件', 'warning'); return }
    if (file.size > 2 * 1024 * 1024) { store.toast('图片不能超过 2MB', 'warning'); return }
    adFileUploading.value = true
    const reader = new FileReader()
    reader.onload = () => {
      const base64 = reader.result as string
      const imgTag = `<img src="${base64}" alt="${file.name}" style="max-width:100%" />`
      const ta = document.querySelector('.ad-html-textarea') as HTMLTextAreaElement
      if (ta) {
        const start = ta.selectionStart; const end = ta.selectionEnd
        adForm.html_content = adForm.html_content.substring(0, start) + imgTag + adForm.html_content.substring(end)
      } else {
        adForm.html_content += imgTag
      }
      adFileUploading.value = false; store.toast('图片已插入', 'success')
    }
    reader.onerror = () => { adFileUploading.value = false; store.toast('图片读取失败', 'error') }
    reader.readAsDataURL(file); (e.target as HTMLInputElement).value = ''
  }

  return {
    // YPay
    ypayTab, ypayForm, ypaySaving, pairQrTs, pairQrLoading, downloadQrLoading,
    pairQrImage, downloadQrImage, ypayLoaded, ypayStatus, ypayTesting, ypayTestResult,
    ypayOrders, ypayOrdersTotal, ypayOrdersPage, ypayOrderStatusFilter, ypayOrderFilters,
    loadingYpayOrders, ypayAccounts, loadingAccounts, showAccountModal, editingAccount,
    accountForm, savingAccount, showCertFields, showChannelTest, channelTestAccount,
    channelTestLoading, channelTestChecks, channelTestQrImage, channelTestAllOk,
    qrUploading, qrFileInput,
    payTypeLabels, ypayStateLabels, typeLabels, defaultCodes, wxAccounts, aliAccounts,
    channelCodeLabels, channelCodeHelp, codeLabel, fmtHeartbeat, genRandomStr,
    triggerQrUpload, onQrFileChange, resetAccountForm, openAddAccount, openEditAccount,
    closeAccountModal, loadAccounts, saveAccount, deleteAccount, toggleAccount, testChannel,
    loadYpay, saveYpaySettings, saveYpayKeyOnly, regenerateYpayKey, loadPairQr,
    loadYpayOrders, closeExpiredYpayOrders, clearYpayOrderHistory,
    runYpayTest, resetYpayConnection,
    // Ads
    adsList, loadingAds, showAdModal, editingAd, adForm, savingAd,
    adFileInput, adImgInput, adFileUploading,
    loadAds, openCreateAd, openEditAd, saveAd, toggleAdActive, deleteAd,
    triggerAdFileUpload, triggerAdImgUpload, onAdFileChange, onAdImgChange,
  }
}
