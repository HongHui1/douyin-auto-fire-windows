DOUYIN_CHAT_URL = "https://www.douyin.com/chat"

# Ordered alternatives keep page-specific changes isolated from the workflow.
LOGIN_MARKERS = (
    'text=私信',
    'input[placeholder*="搜索"]',
    '[role="textbox"][placeholder*="搜索"]',
)
LOGIN_REQUIRED_MARKERS = (
    # 「扫描二维码登录」是登录弹窗的标题，只出现在真正的登录墙里。
    'text=扫码登录',
    # 以下两个是登录墙标题/按钮的精确文案。
    'text=验证码登录',
    'text=密码登录',
    # 兜底：必须同时存在登录墙文案和手机号输入框才算登录墙。
    # 单独一个「登录后…」在未登录的首页/私信页上到处都有，不能作为判定依据，
    # 否则会把「渲染慢」误判成「登录失效」。
    'div:has-text("扫码登录"):has(input[type="tel"])',
    'div:has-text("验证码登录"):has(input[type="tel"])',
)
RISK_MARKERS = (
    'text=安全验证',
    'text=完成验证',
    'text=验证身份',
)
SEARCH_INPUTS = (
    'input[placeholder*="搜索"]',
    'input[placeholder="搜索"]',  # 精确匹配备用 selector，兼容慢渲染时属性值变化
    '[role="textbox"][placeholder*="搜索"]',
    'input[aria-label*="搜索"]',
    '[role="textbox"][aria-label*="搜索"]',
)
CHAT_PANEL_MARKERS = (
    '[class*="RightPanelHeader"]',
    '[class*="chatHeader"]',
    '[class*="ChatHeader"]',
    '[class*="messageContent"]',
    '[class*="chatContent"]',
    '[class*="MessagePanel"]',
)
MESSAGE_INPUTS = (
    '[data-contents="true"]',
    '.DraftEditor-editor [contenteditable="true"]',
    '.DraftEditor-root [contenteditable="true"]',
    '[contenteditable="true"][data-placeholder*="发送消息"]',
    '[contenteditable="true"][aria-label*="消息"]',
    '[contenteditable="true"]',
    'textarea[placeholder*="消息"]',
)
IMAGE_INPUTS = ('input[type="file"][accept*="image"]', 'input[type="file"]')
STICKER_BUTTONS = (
    'svg.messageMsgInputiconAction',
    'button[aria-label*="表情"]',
    '[role="button"][aria-label*="表情"]',
    '[title*="表情"]',
)
STICKER_PANELS = (
    '.componentsemojiemojiPanel',
    '[class*="emojiPanel"]',
    '[role="dialog"]',
    '[class*="sticker"]',
)
