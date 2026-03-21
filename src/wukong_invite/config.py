"""可配置常量（URL 来自官网前端 bundle 中的互动中台数据接口）。"""

# 钉钉悟空页 bundle 内嵌的 JSONP 地址（img_url 回调返回邀请码展示图 CDN URL）
HUDONG_JSONP_BASE = (
    "https://hudong.alicdn.com/api/data/v2/438eae9715f945468d599660d2d92aeb.js"
)
JSONP_CALLBACK = "img_url"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)
