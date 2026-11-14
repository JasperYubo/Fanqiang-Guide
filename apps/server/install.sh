#!/bin/bash
#=============================================================================
# 华润网络助手 — 跨境电商 & AI 生产力加速器
# VMESS + WS + TLS + CDN · 内置站点模板 · 内置 PicoClaw + DeepSeek 助手
# Copyright (c) 2026 JiamiDog. MIT; see LICENSE. HuaRun adaptation 2026.
#=============================================================================


VERSION="1.0.0"
DOCS_URL="https://fanqiang.guide/server/"
PICO_VERSION="v0.3.1"
PICO_SHA_X86="86f0fe84aa55279352edbe13adfca484a03bcf189e2030b25e34628089069c3f"
PICO_SHA_ARM="e78ab0de05d000698ff8b32458e71cb3134e52e9eaf540e3323a72e9914de060"
AI_MODEL="deepseek-flash"
AI_PROVIDER="deepseek"
AI_API_BASE="https://api.deepseek.com/v1"

#=== 出厂白名单：跨境出海必备的根域名 ===========================================
# 一行一组、空格分隔；匹配含全部子域名。加减域名只改这里：安装时写进 whitelist.txt、
# 写进 xray 路由、也写进 huarun 的「恢复默认」。改完跑一遍 bash -n 和真机安装。
DEFAULT_DOMAINS="$(sed -e 's/#.*//' <<'DOMAINS' | tr -s ' \n' ' ' | sed -e 's/^ //' -e 's/ $//'
# 谷歌与 YouTube
google.com gstatic.com googleapis.com googleusercontent.com googletagmanager.com google-analytics.com googleadservices.com googlesyndication.com doubleclick.net googlevideo.com ggpht.com gvt1.com gvt2.com gmail.com youtube.com youtu.be ytimg.com withgoogle.com blogger.com blogspot.com goo.gl g.co recaptcha.net firebaseio.com firebaseapp.com appspot.com web.app admob.com android.com
# 微软与必应
microsoft.com bing.com bing.net live.com outlook.com hotmail.com office.com office365.com microsoftonline.com msftauth.net msauth.net msecnd.net windows.net windows.com azure.com azureedge.net msn.com skype.com onedrive.com sharepoint.com visualstudio.com clarity.ms
# 苹果
apple.com icloud.com mzstatic.com cdn-apple.com apple-dns.net me.com
# Meta 全家
facebook.com fb.com fbcdn.net facebook.net fbsbx.com meta.com messenger.com instagram.com cdninstagram.com threads.net whatsapp.com whatsapp.net
# TikTok 与字节
tiktok.com tiktokv.com tiktokcdn.com tiktokcdn-us.com tiktokglobalshop.com byteoversea.com ibyteimg.com ttwstatic.com musical.ly bytedance.com capcut.com
# X
x.com twitter.com twimg.com t.co
# 其他社媒与社区
linkedin.com licdn.com pinterest.com pinimg.com reddit.com redd.it redditstatic.com redditmedia.com snapchat.com snap.com sc-cdn.net tumblr.com quora.com medium.com substack.com vimeo.com vimeocdn.com twitch.tv ttvnw.net discord.com discordapp.com discord.gg telegram.org telegram.me t.me telesco.pe line.me line-apps.com naver.com kakao.com viber.com signal.org flickr.com imgur.com giphy.com tenor.com
# 亚马逊
amazon.com amazon.ca amazon.com.mx amazon.co.uk amazon.de amazon.fr amazon.it amazon.es amazon.nl amazon.se amazon.pl amazon.com.be amazon.co.jp amazon.in amazon.sg amazon.com.au amazon.ae amazon.sa amazon.com.br amazon.com.tr amazon.eg media-amazon.com ssl-images-amazon.com images-amazon.com amazonaws.com awsstatic.com amazon-adsystem.com amazontrust.com a2z.com amzn.to amzn.com
# 其他电商平台
ebay.com ebay.co.uk ebay.de ebay.com.au ebay.ca ebay.fr ebay.it ebay.es ebaystatic.com ebayimg.com ebaydesc.com ebayrtm.com etsy.com etsystatic.com walmart.com walmartimages.com target.com bestbuy.com homedepot.com wayfair.com costco.com newegg.com overstock.com temu.com shein.com wish.com mercadolibre.com mercadolivre.com.br mercadopago.com allegro.pl bol.com otto.de cdiscount.com fnac.com rakuten.co.jp rakuten.com zalando.com asos.com ozon.ru wildberries.ru coupang.com flipkart.com noon.com jumia.com lazada.com shopee.com tokopedia.com qoo10.jp
# 独立站与建站
shopify.com myshopify.com shopifycdn.com shopifysvc.com shopify.dev shop.app bigcommerce.com woocommerce.com wix.com wixstatic.com squarespace.com squarespace-cdn.com webflow.com webflow.io wordpress.com wordpress.org wp.com w.org gravatar.com godaddy.com namecheap.com name.com dynadot.com porkbun.com cloudflare.com cloudflareinsights.com vercel.com vercel.app netlify.com netlify.app github.com githubusercontent.com githubassets.com github.io gitlab.com npmjs.com jsdelivr.net unpkg.com bootstrapcdn.com jquery.com fontawesome.com typekit.net
# 收款与支付
paypal.com paypalobjects.com stripe.com stripe.network payoneer.com wise.com airwallex.com worldfirst.com adyen.com klarna.com afterpay.com affirm.com squareup.com braintreegateway.com 2checkout.com coinbase.com
# 广告、联盟与分析
criteo.com taboola.com outbrain.com appsflyer.com adjust.com branch.io impact.com cj.com shareasale.com awin.com linksynergy.com partnerize.com clickbank.com semrush.com ahrefs.com similarweb.com moz.com hotjar.com mixpanel.com segment.com amplitude.com optimizely.com
# 营销、客服与评价
mailchimp.com klaviyo.com sendgrid.com hubspot.com hsforms.com brevo.com omnisend.com privy.com gorgias.com zendesk.com zdassets.com intercom.com intercomcdn.com freshdesk.com tidio.com crisp.chat typeform.com surveymonkey.com trustpilot.com yotpo.com judge.me loox.io
# 物流与履约
dhl.com fedex.com ups.com usps.com 17track.net aftership.com shipstation.com easyship.com goshippo.com printful.com printify.com
# 办公与协作
notion.so notion.site slack.com slack-edge.com zoom.us canva.com figma.com dropbox.com box.com trello.com atlassian.com asana.com airtable.com calendly.com docusign.com grammarly.com deepl.com miro.com loom.com evernote.com zoho.com
# AI 工具
openai.com chatgpt.com oaistatic.com oaiusercontent.com anthropic.com claude.ai perplexity.ai midjourney.com x.ai grok.com huggingface.co replicate.com elevenlabs.io runwayml.com stability.ai
# 资讯、参考与接单
wikipedia.org wikimedia.org stackoverflow.com stackexchange.com producthunt.com techcrunch.com bbc.com bbc.co.uk nytimes.com reuters.com bloomberg.com wsj.com cnn.com theguardian.com forbes.com duckduckgo.com yahoo.com yahoo.co.jp archive.org upwork.com fiverr.com freelancer.com
# CDN 与基础设施
cloudfront.net akamaihd.net akamaized.net akamai.net fastly.net fastlylb.net digitaloceanspaces.com digitalocean.com vultr.com linode.com hcaptcha.com sentry.io imgix.net
DOMAINS
)"
# xray 路由用的 JSON 数组："domain:a","domain:b"
domainJson() { local d out=""; for d in $DEFAULT_DOMAINS; do out+="\"domain:${d}\","; done; echo "${out%,}"; }

#=== 颜色 ===================================================================
RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
BLUE="\033[36m"; PLAIN="\033[0m"

#=== 全局变量 ===============================================================
XRAY_PORT=""; UUID=""; WS_PATH=""; DOMAIN=""; SITE_TYPE=""
PMT=""; CMD_INSTALL=""
MEM_MB=0; SWAP_MADE=0
INFO_FILE="/etc/huarun/info.json"
SITE_DIR="/usr/share/nginx/huarun"
TPL_DIR="/usr/share/nginx/huarun-templates"
CERT_DIR="/etc/nginx/ssl/huarun"
ACME_HOME="/etc/huarun/acme"
ACME_BIN="/usr/local/lib/huarun/acme.sh"
CRON_FILE="/etc/cron.d/huarun-acme"
BBR_CONF="/etc/sysctl.d/99-huarun-bbr.conf"
SWAP_FILE="/var/lib/huarun/swapfile"
AI_HOME="/etc/huarun/assistant"
AI_TPL="/etc/huarun/assistant-template"

# 命令行参数（不给就交互问）
OPT_DOMAIN=""; OPT_SITE=""; OPT_YES=0; OPT_JSON=0; OPT_NOSWAP=0; OPT_FORCE_OS=0
AI_KEY="${HUARUN_API_KEY:-}"
export -n AI_KEY
unset HUARUN_API_KEY

colorEcho() { echo -e "${1}${*:2}${PLAIN}"; }

usage() {
    cat <<USAGE
用法: bash install.sh [选项]
  --domain <域名>   已解析到本机的域名；不给则交互问，直接回车用 <ip>.sslip.io
  --site <1-4>      站点类型：1 文档站 2 加密工具站 3 学生福利导航站 4 不要站点（默认 1）
  --yes             不问任何问题（域名缺省用 sslip.io）
  --json            装完只输出一段 JSON（隐含 --yes）
  --no-swap         内存小于 1G 时也不建 swap
  --force-os        内存小的机器上硬装重系统
先到 https://platform.deepseek.com 充值 10 元起步并创建 API Key。
10 元是建议起步金额，不是平台最低充值额或时长承诺。
环境变量 HUARUN_API_KEY 可以代替隐藏交互输入。助手为必装组件。
USAGE
}

parseArgs() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --domain) [[ $# -ge 2 && "$2" != --* ]] || { echo "--domain 缺少域名" >&2; return 1; }; OPT_DOMAIN="$2"; shift 2 ;;
            --domain=*) OPT_DOMAIN="${1#*=}"; shift ;;
            --site) [[ $# -ge 2 && "$2" != --* ]] || { echo "--site 缺少选项" >&2; return 1; }; OPT_SITE="$2"; shift 2 ;;
            --site=*) OPT_SITE="${1#*=}"; shift ;;
            --yes|-y) OPT_YES=1; shift ;;
            --json) OPT_JSON=1; OPT_YES=1; shift ;;
            --no-swap) OPT_NOSWAP=1; shift ;;
            --force-os) OPT_FORCE_OS=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) colorEcho "$RED" "未知参数：$1"; usage; exit 1 ;;
        esac
    done
}

# JSON 模式下把人看的输出压掉
say() { [[ $OPT_JSON -eq 1 ]] && return 0; colorEcho "$@"; }

#=== 1. 系统检测 =============================================================
checkSystem() {
    [[ $EUID -ne 0 ]] && colorEcho "$RED" "请以root身份执行" && exit 1
    if which apt &>/dev/null; then
        PMT="apt"; CMD_INSTALL="apt install -y"
    elif which yum &>/dev/null; then
        PMT="yum"; CMD_INSTALL="yum install -y"
    else
        colorEcho "$RED" "不受支持的系统"; exit 1
    fi
    command -v systemctl >/dev/null || { echo "需要使用 systemd 的 Linux 服务器" >&2; return 1; }
    command -v curl >/dev/null || { echo "请先安装 curl，再运行本脚本" >&2; return 1; }
    say "$GREEN" "✓ 系统检测通过"
}

# Fail before package installation, swap, or service changes.
checkConflicts() {
    if [[ -e "$INFO_FILE" ]]; then
        echo "这台机器已装华润。使用 huarun chat / doctor / assistant setup；不会覆盖连接参数与白名单。" >&2
        return 1
    fi
    if command -v nginx >/dev/null 2>&1 || command -v xray >/dev/null 2>&1 || [[ -e /usr/local/etc/xray/config.json || -e /etc/nginx/conf.d/huarun.conf ]]; then
        echo "发现已有 Nginx / Xray。请使用空白 VPS；本安装不会接管已有网站或网络服务。" >&2
        return 1
    fi
    local listeners
    if command -v ss >/dev/null 2>&1; then
        listeners=$(ss -H -lnt 2>/dev/null | awk '{print $4}' | grep -E ':(80|443)$' || true)
    else
        listeners=$(awk '$4 == "0A" && $2 ~ /:(0050|01BB)$/ {print $2}' /proc/net/tcp /proc/net/tcp6 2>/dev/null)
    fi
    [[ -z "$listeners" ]] || { echo "80/443 已被占用，请使用空白 VPS。" >&2; return 1; }
}

#=== 1.5 装前检测：内存、系统、swap =========================================
preflight() {
    MEM_MB=$(awk '/MemTotal/{printf "%d", $2/1024}' /proc/meminfo)
    local os_id="unknown" os_ver="" pretty="unknown"
    if [[ -f /etc/os-release ]]; then
        os_id=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')
        os_ver=$(sed -n 's/^VERSION_ID=//p' /etc/os-release | tr -d '"')
        pretty=$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release | tr -d '"')
    fi
    say "$BLUE" "内存 ${MEM_MB}MB，系统 ${pretty}"
    if [[ $MEM_MB -lt 700 && $OPT_FORCE_OS -eq 0 ]]; then
        local heavy=0
        case "$os_id" in
            centos|rhel|rocky|almalinux|fedora) heavy=1 ;;
            ubuntu) [[ "${os_ver%%.*}" -ge 22 ]] && heavy=1 ;;
        esac
        if [[ $heavy -eq 1 ]]; then
            colorEcho "$RED" "这台机器只有 ${MEM_MB}MB 内存，${pretty} 太重，装上去会卡会崩。"
            colorEcho "$YELLOW" "请到服务商面板把系统重装成 Debian 12，再回来跑这一行命令。（硬要装：加 --force-os）"
            exit 1
        fi
    fi
    if [[ $OPT_NOSWAP -eq 0 && $MEM_MB -lt 1024 ]] && ! swapon --show 2>/dev/null | grep -q .; then
        say "$BLUE" "内存不足 1G 且没有 swap，建 512MB swap 当保险..."
        mkdir -p /var/lib/huarun
        if [[ -e "$SWAP_FILE" ]]; then say "$YELLOW" "已有华润 swap 文件，保留并跳过"; return 0; fi
        if [[ ! -f "$SWAP_FILE" ]]; then
            if ! fallocate -l 512M "$SWAP_FILE" 2>/dev/null; then
                dd if=/dev/zero of="$SWAP_FILE" bs=1M count=512 status=none 2>/dev/null || true
            fi
        fi
        if [[ -f "$SWAP_FILE" ]] && chmod 600 "$SWAP_FILE" && mkswap "$SWAP_FILE" >/dev/null 2>&1 && swapon "$SWAP_FILE" 2>/dev/null; then
            grep -q "^${SWAP_FILE} " /etc/fstab 2>/dev/null || echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
            SWAP_MADE=1
            say "$GREEN" "✓ swap 已启用"
        else
            rm -f "$SWAP_FILE"
            say "$YELLOW" "△ swap 建不了，跳过"
        fi
    fi
}

#=== 2. 用户输入 =============================================================
getData() {
    say "$BLUE" ""
    [[ $OPT_JSON -eq 0 ]] && echo -e "${BLUE}华润网络助手 跨境电商加速器 v${VERSION}${PLAIN}" && echo ""
    DOMAIN="$OPT_DOMAIN"
    if [[ -z "$DOMAIN" && $OPT_YES -eq 0 ]]; then
        read -r -p "请输入你的域名（已解析到本机；没有就直接回车，用 sslip.io 域名申请证书）: " DOMAIN
    fi
    if [[ -z "$DOMAIN" ]]; then
        local ip
        ip=$(curl -s4m8 https://ip.gs || curl -s4m8 https://ifconfig.me || true)
        [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { colorEcho "$RED" "拿不到本机公网 IP，请用 --domain 指定域名"; exit 1; }
        DOMAIN="$(echo "$ip" | tr . -).sslip.io"
        say "$YELLOW" "没有域名，用 ${DOMAIN}"
    fi
    DOMAIN=${DOMAIN,,}
    [[ ${#DOMAIN} -le 253 && "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]] || { echo "域名格式不正确" >&2; return 1; }
    say "$BLUE" "域名：$DOMAIN"

    SITE_TYPE="$OPT_SITE"
    if [[ -z "$SITE_TYPE" && $OPT_YES -eq 0 ]]; then
        echo ""; echo "请选择站点类型[默认：1]:"
        echo "  1) 文档站"
        echo "  2) 加密工具站"
        echo "  3) 学生福利导航站"
        echo "  4) 不需要站点"
        read -r -p "选择[1]: " SITE_TYPE
    fi
    SITE_TYPE=${SITE_TYPE:-1}
    [[ "$SITE_TYPE" =~ ^[1-4]$ ]] || { echo "站点类型必须是 1 到 4" >&2; return 1; }
    say "$BLUE" "站点类型：$SITE_TYPE"
}

#=== 2.5 收 AI 钥匙（不进命令行、不进对话） =================================
askKey() {
    if [[ -z "$AI_KEY" && $OPT_YES -eq 0 ]]; then
        echo ""
        colorEcho "$BLUE" "先到 https://platform.deepseek.com 充值 10 元起步，创建并复制 API Key。"
        echo "余额付给 DeepSeek；10 元是起步建议，不是最低充值限制。"
        echo "接下来把 PicoClaw 助手装进这台 VPS，直接用中文让它检查和修复。"
        read -r -s -p "粘贴 DeepSeek API Key（不回显）: " AI_KEY || return 1
        echo ""
    fi
    [[ "$AI_KEY" =~ ^sk-[A-Za-z0-9_-]{8,}$ ]] || { echo "缺少或无效的 DeepSeek API Key；尚未安装。交互粘贴或设置 HUARUN_API_KEY。" >&2; return 1; }
    local code response
    response=$(printf 'header = "Authorization: Bearer %s"\n' "$AI_KEY" | curl -s -w '\n%{http_code}' --max-time 20 --config - "${AI_API_BASE}/models" || true)
    code="${response##*$'\n'}"
    [[ "$code" == "200" ]] || { echo "DeepSeek Key 校验失败（HTTP ${code}），请检查 Key 和网络；尚未安装。" >&2; return 1; }
    grep -Eq '"id"[[:space:]]*:[[:space:]]*"deepseek-flash"' <<< "$response" || { echo "账户未返回 deepseek-flash，尚未安装。" >&2; return 1; }
    say "$GREEN" "✓ DeepSeek Key 与模型校验通过"
}

prepareAssistant() {
    local asset sha
    case "$(uname -m)" in
        x86_64|amd64) asset="picoclaw_Linux_x86_64.tar.gz"; sha="$PICO_SHA_X86" ;;
        aarch64|arm64) asset="picoclaw_Linux_arm64.tar.gz"; sha="$PICO_SHA_ARM" ;;
        *) echo "当前架构没有已验证的 PicoClaw 包，未开始安装。" >&2; return 1 ;;
    esac
    PICO_TMP=$(mktemp -d)
    curl -fsSL --retry 2 "https://github.com/sipeed/picoclaw/releases/download/${PICO_VERSION}/${asset}" -o "$PICO_TMP/p.tgz" || { echo "PicoClaw 下载失败，未开始安装。" >&2; return 1; }
    echo "${sha}  $PICO_TMP/p.tgz" | sha256sum -c - >/dev/null 2>&1 || { echo "PicoClaw 校验失败，未开始安装。" >&2; return 1; }
    tar xzf "$PICO_TMP/p.tgz" -C "$PICO_TMP"
    PICO_BIN_READY=$(find "$PICO_TMP" -maxdepth 2 -type f -name picoclaw | head -1)
    [[ -n "$PICO_BIN_READY" ]] || { echo "PicoClaw 包内没有可执行文件。" >&2; return 1; }
}

#=== 3. VPS质量检测 ===========================================================
vps_check() {
    say "$BLUE" ""; say "$BLUE" "VPS质量检测..."
    DNS_OK=0; NET_OK=0
    getent ahosts "$DOMAIN" >/dev/null 2>&1 && DNS_OK=1
    curl -fsS --max-time 5 https://1.1.1.1 >/dev/null 2>&1 && NET_OK=1
    [[ $DNS_OK -eq 1 ]] && say "$GREEN" "✓ DNS解析正常" || say "$RED" "✗ DNS解析失败"
    [[ $NET_OK -eq 1 ]] && say "$GREEN" "✓ 出站网络正常" || say "$RED" "✗ 出站网络不通"
    LATENCY=$(ping -c 3 google.com 2>/dev/null | tail -1 | awk -F'/' '{print $5}') || true
    [[ -n "$LATENCY" ]] && say "$GREEN" "✓ 延迟: ${LATENCY}ms" || say "$YELLOW" "△ 无法测延迟"
    BBR=$(sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep bbr || true)
    [[ -n "$BBR" ]] && say "$GREEN" "✓ BBR已开启" || say "$YELLOW" "△ BBR未开启，将自动开启"
}

#=== 4. 安装依赖 =============================================================
installDeps() {
    say "$BLUE" ""; say "$BLUE" "安装依赖..."
    if [[ "$PMT" == "apt" ]]; then
        waited=0
        while fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; do
            if [[ $waited -ge 120 ]]; then
                say "$YELLOW" "△ apt 锁等了 120 秒还没释放，继续尝试安装"; break
            fi
            sleep 3; waited=$((waited + 3))
        done
        apt update -qq >/dev/null 2>&1 || true
    elif [[ "$PMT" == "yum" ]]; then
        yum install -y epel-release >/dev/null 2>&1 || true
    fi
    for pkg in curl wget unzip jq openssl socat nginx tar python3 iproute2 ca-certificates; do
        if ! $CMD_INSTALL "$pkg" >/dev/null 2>&1; then
            colorEcho "$RED" "依赖安装失败: $pkg"; exit 1
        fi
    done
    if ! which nginx &>/dev/null && [[ "$PMT" == "yum" ]]; then
        cat > /etc/yum.repos.d/nginx.repo << 'NGINXREPO'
[nginx-stable]
name=nginx stable repo
baseurl=https://nginx.org/packages/centos/$releasever/$basearch/
gpgcheck=1
enabled=1
repo_gpgcheck=1
gpgkey=https://nginx.org/keys/nginx_signing.key
NGINXREPO
        $CMD_INSTALL nginx 2>/dev/null
    fi
    systemctl enable nginx 2>/dev/null || true
    say "$GREEN" "✓ 依赖安装完成"
}

#=== 5. 安装Xray =============================================================
installXray() {
    say "$BLUE" ""; say "$BLUE" "安装Xray..."
    XRAY_URL="https://raw.githubusercontent.com/XTLS/Xray-install/e741a4f56d368afbb9e5be3361b40c4552d3710d/install-release.sh"
    XRAY_SHA256="7f70c95f6b418da8b4f4883343d602964915e28748993870fd554383afdbe555"
    tmp_xray=$(mktemp)
    curl -fsSL "$XRAY_URL" -o "$tmp_xray"
    echo "${XRAY_SHA256}  ${tmp_xray}" | sha256sum -c - >/dev/null || {
        colorEcho "$RED" "Xray安装脚本校验失败"; rm -f "$tmp_xray"; exit 1
    }
    bash "$tmp_xray" install >/dev/null 2>&1 || bash "$tmp_xray" install
    rm -f "$tmp_xray"
    systemctl enable xray 2>/dev/null || true
    say "$GREEN" "✓ Xray安装完成"
}

#=== 6. 防火墙与 SELinux：只放行，不关闭 =====================================
openFirewall() {
    say "$BLUE" ""; say "$BLUE" "检查防火墙..."
    if systemctl is-active --quiet firewalld 2>/dev/null; then
        firewall-cmd --permanent --add-service=http >/dev/null 2>&1 || true
        firewall-cmd --permanent --add-service=https >/dev/null 2>&1 || true
        firewall-cmd --reload >/dev/null 2>&1 || true
        say "$GREEN" "✓ firewalld 已放行 80/443，其余规则不动"
    fi
    if which ufw &>/dev/null && ufw status 2>/dev/null | grep -q '^Status: active'; then
        ufw allow 80/tcp >/dev/null 2>&1 || true
        ufw allow 443/tcp >/dev/null 2>&1 || true
        say "$GREEN" "✓ ufw 已放行 80/443，其余规则不动"
    fi
    if which getenforce &>/dev/null && [[ "$(getenforce 2>/dev/null)" == "Enforcing" ]]; then
        setsebool -P httpd_can_network_connect 1 2>/dev/null || true
        say "$GREEN" "✓ SELinux 保持开启，已允许 nginx 连接本机 Xray 端口"
    fi
    say "$GREEN" "✓ 防火墙检查完成"
}

#=== 7. 申请证书 =============================================================
installCert() {
    say "$BLUE" ""; say "$BLUE" "申请证书..."
    systemctl stop nginx 2>/dev/null || true
    systemctl stop xray 2>/dev/null || true
    sleep 2
    res=$(ss -ntlp 2>/dev/null | grep -E ':(80|443)\s' || true)
    if [[ -n "$res" ]]; then
        colorEcho "$RED" "80/443端口被其他进程占用："
        echo "$res"
        colorEcho "$YELLOW" "请释放端口后重试"; exit 1
    fi

    $CMD_INSTALL socat openssl >/dev/null 2>&1 || true
    if [[ "$PMT" == "yum" ]]; then
        $CMD_INSTALL cronie >/dev/null 2>&1 || true
        systemctl start crond 2>/dev/null || true; systemctl enable crond 2>/dev/null || true
    else
        $CMD_INSTALL cron >/dev/null 2>&1 || true
        systemctl start cron 2>/dev/null || true; systemctl enable cron 2>/dev/null || true
    fi

    ACME_URL="https://raw.githubusercontent.com/acmesh-official/acme.sh/3.1.3/acme.sh"
    ACME_SHA256="66171c3113f2e36569572edb1656962d63c72862a57e03cbd2a066adaad5e588"
    tmp_acme=$(mktemp)
    curl -fsSL "$ACME_URL" -o "$tmp_acme"
    echo "${ACME_SHA256}  ${tmp_acme}" | sha256sum -c - >/dev/null || {
        colorEcho "$RED" "acme.sh校验失败"; rm -f "$tmp_acme"; exit 1
    }
    mkdir -p /usr/local/lib/huarun
    install -m 0755 "$tmp_acme" "$ACME_BIN"
    rm -f "$tmp_acme"
    mkdir -p "$ACME_HOME"
    "$ACME_BIN" --home "$ACME_HOME" --set-default-ca --server letsencrypt >/dev/null 2>&1 || true
    if ! "$ACME_BIN" --home "$ACME_HOME" --issue -d "${DOMAIN}" --keylength ec-256 --standalone --force --server letsencrypt \
        --pre-hook "systemctl stop nginx 2>/dev/null || true" \
        --post-hook "systemctl start nginx 2>/dev/null || true" >/dev/null 2>&1; then
        colorEcho "$RED" "证书申请失败。常见原因：域名没解析到本机、80端口被云防火墙挡住、Let's Encrypt 频率限制"
        colorEcho "$YELLOW" "详细日志：${ACME_HOME}/acme.sh.log"
        exit 1
    fi

    mkdir -p "$CERT_DIR"; chmod 700 "$CERT_DIR"
    "$ACME_BIN" --home "$ACME_HOME" --install-cert -d "${DOMAIN}" --ecc \
        --key-file "${CERT_DIR}/${DOMAIN}.key" \
        --fullchain-file "${CERT_DIR}/fullchain.cer" \
        --reloadcmd "systemctl is-active --quiet nginx && systemctl reload nginx || true" >/dev/null 2>&1

    [[ -f "${CERT_DIR}/fullchain.cer" ]] || {
        colorEcho "$RED" "证书安装失败"; exit 1
    }

    cat > "$CRON_FILE" << CRONEOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
23 3 * * * root ${ACME_BIN} --cron --home ${ACME_HOME} > /dev/null 2>&1
CRONEOF
    chmod 644 "$CRON_FILE"
    say "$GREEN" "✓ 证书申请成功，自动续期已登记：${CRON_FILE}"
}

#=== 8. 生成配置 =============================================================
generateConfig() {
    say "$BLUE" ""; say "$BLUE" "生成配置..."

    XRAY_PORT=$(shuf -i 10000-65535 -n 1)
    while ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":${XRAY_PORT}$"; do
        XRAY_PORT=$(shuf -i 10000-65535 -n 1)
    done
    UUID=$(cat /proc/sys/kernel/random/uuid)
    len=$(shuf -i5-12 -n1)
    # 有限输入，不靠 SIGPIPE 收尾（SIGPIPE 被忽略的环境里 fold 会对着无限流永远不结束）
    ws=$(head -c 512 /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c "$len")
    WS_PATH="/$ws"

    mkdir -p /usr/local/etc/xray
    cat > /usr/local/etc/xray/config.json << XEOF
{
  "log": {
    "loglevel": "warning",
    "access": "/var/log/xray/access.log",
    "error": "/var/log/xray/error.log"
  },
  "inbounds": [{
    "tag": "vmess-ws",
    "port": ${XRAY_PORT},
    "listen": "127.0.0.1",
    "protocol": "vmess",
    "settings": {
      "clients": [{"id": "${UUID}"}]
    },
    "streamSettings": {
      "network": "ws",
      "wsSettings": {"path": "${WS_PATH}"}
    },
    "sniffing": {
      "enabled": true,
      "destOverride": ["http", "tls", "quic"],
      "routeOnly": true
    }
  }],
  "outbounds": [
    {"protocol": "freedom", "tag": "direct"},
    {"protocol": "blackhole", "tag": "blocked"}
  ],
  "routing": {
    "domainStrategy": "IPIfNonMatch",
    "rules": [
      {
        "type": "field",
        "domain": [$(domainJson)],
        "outboundTag": "direct"
      },
      {
        "type": "field",
        "port": "0-65535",
        "outboundTag": "blocked"
      }
    ]
  }
}
XEOF
    writeNginxConf
    say "$GREEN" "✓ 配置生成完成"
}

# nginx 配置单独一个函数：huarun fix 也能重建它（参数从 info.json 来）
writeNginxConf() {
    local listen6="" listen6_80=""
    [[ -f /proc/net/if_inet6 ]] && listen6="    listen [::]:443 ssl http2;" && listen6_80="    listen [::]:80;"
    mkdir -p /etc/nginx/conf.d 2>/dev/null || true
    cat > /etc/nginx/conf.d/huarun.conf << NEOF
server {
    listen 443 ssl http2;
${listen6}
    server_name ${DOMAIN};
    ssl_certificate ${CERT_DIR}/fullchain.cer;
    ssl_certificate_key ${CERT_DIR}/${DOMAIN}.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location ${WS_PATH} {
        proxy_redirect off;
        proxy_pass http://127.0.0.1:${XRAY_PORT};
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }

    location / {
        root ${SITE_DIR};
        index index.html;
        try_files \$uri \$uri/ =404;
    }
}
server {
    listen 80;
${listen6_80}
    server_name ${DOMAIN};
    return 301 https://\$host\$request_uri;
}
NEOF
}

#=== 9. 站点模板（随脚本走，不依赖外部服务） ===============================
installTemplates() {
    mkdir -p "$TPL_DIR" "$SITE_DIR"

    cat > "${TPL_DIR}/1.html" << 'TPL'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--ink:#1f2933;--muted:#616e7c;--line:#e4e7eb;--accent:#2f6fed;--bg:#fafbfc}
*{box-sizing:border-box}body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header{border-bottom:1px solid var(--line);background:#fff}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
nav{display:flex;justify-content:space-between;align-items:center;height:60px}
nav b{font-size:18px}nav a{color:var(--muted);text-decoration:none;margin-left:20px;font-size:14px}
.hero{padding:64px 0 40px}.hero h1{font-size:36px;margin:0 0 12px}.hero p{color:var(--muted);max-width:620px;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;padding:24px 0 64px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px}.card h3{margin:0 0 8px;font-size:17px}.card p{margin:0;color:var(--muted);font-size:14px}
code{background:#eef2f7;padding:2px 6px;border-radius:4px;font-size:13px}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:13px;padding:24px 0}
</style>
</head>
<body>
<header><div class="wrap"><nav><b>{{TITLE}}</b><span><a href="#start">Getting started</a><a href="#ref">Reference</a><a href="#faq">FAQ</a></span></nav></div></header>
<main class="wrap">
<section class="hero"><h1>{{TITLE}}</h1><p>Guides, endpoint references and integration notes for the current release. All examples use the stable API surface; deprecated calls are marked in the changelog.</p></section>
<section class="grid" id="start">
<div class="card"><h3>Quick start</h3><p>Install the SDK, create a token and make your first request in under five minutes. Sample projects are available for Node.js, Python and Go.</p></div>
<div class="card" id="ref"><h3>Endpoint reference</h3><p>Every route documented with request and response schemas, rate limits and error codes. Try requests directly from the reference pages.</p></div>
<div class="card"><h3>Authentication</h3><p>Token-based access with scoped permissions. Rotate credentials without downtime using overlapping validity windows.</p></div>
<div class="card"><h3>Webhooks</h3><p>Subscribe to events, verify signatures and replay missed deliveries from the dashboard. Retries follow an exponential schedule.</p></div>
<div class="card"><h3>Changelog</h3><p>Versioned release notes with migration guides. Breaking changes ship behind a version header for at least 90 days.</p></div>
<div class="card" id="faq"><h3>FAQ</h3><p>Answers to common questions about pagination, idempotency keys, sandbox environments and billing of API usage.</p></div>
</section>
</main>
<footer><div class="wrap">&copy; {{YEAR}} {{TITLE}} &middot; Build <code>{{BUILD}}</code></div></footer>
</body>
</html>
TPL

    cat > "${TPL_DIR}/2.html" << 'TPL'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--ink:#e6edf3;--muted:#8b949e;--line:#30363d;--accent:#3fb950;--bg:#0d1117;--card:#161b22}
*{box-sizing:border-box}body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header{border-bottom:1px solid var(--line)}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
nav{display:flex;justify-content:space-between;align-items:center;height:60px}
nav b{font-size:18px;color:var(--accent)}nav a{color:var(--muted);text-decoration:none;margin-left:20px;font-size:14px}
.hero{padding:64px 0 40px}.hero h1{font-size:36px;margin:0 0 12px}.hero p{color:var(--muted);max-width:620px;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;padding:24px 0 64px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:22px}.card h3{margin:0 0 8px;font-size:17px}.card p{margin:0;color:var(--muted);font-size:14px}
code{background:#21262d;padding:2px 6px;border-radius:4px;font-size:13px}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:13px;padding:24px 0}
</style>
</head>
<body>
<header><div class="wrap"><nav><b>{{TITLE}}</b><span><a href="#hash">Hashing</a><a href="#cipher">Ciphers</a><a href="#keys">Keys</a></span></nav></div></header>
<main class="wrap">
<section class="hero"><h1>{{TITLE}}</h1><p>Browser-side utilities for hashing, encoding and symmetric encryption. Everything runs locally; nothing you paste here leaves your device.</p></section>
<section class="grid">
<div class="card" id="hash"><h3>Hash calculator</h3><p>SHA-256, SHA-512, SHA-1 and MD5 digests of text or files, with hex and Base64 output.</p></div>
<div class="card" id="cipher"><h3>AES encrypt / decrypt</h3><p>AES-GCM with a passphrase-derived key (PBKDF2, 200k iterations). Output is a self-describing Base64 envelope.</p></div>
<div class="card" id="keys"><h3>Key generator</h3><p>Random keys, UUIDs and passphrases from the platform CSPRNG. Choose length, alphabet and separator.</p></div>
<div class="card"><h3>Encoders</h3><p>Base64, Base32, hex, URL and HTML entity encoding with automatic detection of the input format.</p></div>
<div class="card"><h3>JWT inspector</h3><p>Decode headers and claims, check expiry and verify HMAC signatures against a shared secret.</p></div>
<div class="card"><h3>Checksum verify</h3><p>Compare a downloaded file against a published digest. Supports pasted digest lists in the common <code>sha256sum</code> format.</p></div>
</section>
</main>
<footer><div class="wrap">&copy; {{YEAR}} {{TITLE}} &middot; Build <code>{{BUILD}}</code></div></footer>
</body>
</html>
TPL

    cat > "${TPL_DIR}/3.html" << 'TPL'
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{--ink:#222;--muted:#6b7280;--line:#e5e7eb;--accent:#d97706;--bg:#fffdf7}
*{box-sizing:border-box}body{margin:0;font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:var(--ink);background:var(--bg)}
header{border-bottom:1px solid var(--line);background:#fff}
.wrap{max-width:960px;margin:0 auto;padding:0 24px}
nav{display:flex;justify-content:space-between;align-items:center;height:60px}
nav b{font-size:18px;color:var(--accent)}nav a{color:var(--muted);text-decoration:none;margin-left:20px;font-size:14px}
.hero{padding:64px 0 40px}.hero h1{font-size:36px;margin:0 0 12px}.hero p{color:var(--muted);max-width:620px;margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px;padding:24px 0 64px}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:22px}.card h3{margin:0 0 8px;font-size:17px}.card p{margin:0;color:var(--muted);font-size:14px}
code{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:13px}
footer{border-top:1px solid var(--line);color:var(--muted);font-size:13px;padding:24px 0}
</style>
</head>
<body>
<header><div class="wrap"><nav><b>{{TITLE}}</b><span><a href="#software">Software</a><a href="#learning">Learning</a><a href="#life">Campus life</a></span></nav></div></header>
<main class="wrap">
<section class="hero"><h1>{{TITLE}}</h1><p>A curated directory of free tiers, education discounts and open resources for students. Entries are checked each term; expired offers are removed.</p></section>
<section class="grid">
<div class="card" id="software"><h3>Software &amp; cloud credits</h3><p>Developer tools, design suites and cloud platforms that offer free or discounted plans with a verified school email.</p></div>
<div class="card" id="learning"><h3>Courses &amp; libraries</h3><p>Open courseware, textbook archives and journal access programmes available without a subscription.</p></div>
<div class="card" id="life"><h3>Travel &amp; transport</h3><p>Rail cards, airline youth fares and city transit passes with student pricing, sorted by region.</p></div>
<div class="card"><h3>Hardware deals</h3><p>Education stores for laptops and tablets, plus refurbished programmes with warranty.</p></div>
<div class="card"><h3>Scholarships</h3><p>Deadlines and eligibility notes for grants and exchange programmes, updated monthly.</p></div>
<div class="card"><h3>Submit an offer</h3><p>Know a discount that is missing? Send the link and we will verify it before listing.</p></div>
</section>
</main>
<footer><div class="wrap">&copy; {{YEAR}} {{TITLE}} &middot; Build <code>{{BUILD}}</code></div></footer>
</body>
</html>
TPL
    say "$GREEN" "✓ 站点模板已就绪"
}

#=== 10. 白名单 + TOS ========================================================
setupWhitelist() {
    echo "$DEFAULT_DOMAINS" | tr ' ' '
' > /usr/local/etc/xray/whitelist.txt

    cat > /usr/local/etc/xray/TOS.txt << 'TOSEOF'
TERMS OF SERVICE — 华润网络助手 Cross-border Accelerator

华润网络助手 is designed as a network accelerator for cross-border
e-commerce and AI productivity platforms. The default configuration
restricts access to authorized business platforms only.

By removing or modifying the default whitelist, you acknowledge:

1. You are solely responsible for all network traffic routed
   through this software after modification.
2. You will comply with all applicable local and international
   laws and regulations.
3. The developers and contributors of 华润网络助手 bear no liability
   for any use beyond the original cross-border business purpose.
4. This software is provided "AS IS" without warranty of any kind.

If you do not agree, do not modify the whitelist.
TOSEOF

    say "$GREEN" "✓ 白名单 + TOS 已就绪"
}

#=== 11. 开启BBR ==============================================================
enableBBR() {
    say "$BLUE" ""; say "$BLUE" "开启BBR..."
    modprobe tcp_bbr 2>/dev/null || true
    if sysctl net.ipv4.tcp_available_congestion_control 2>/dev/null | grep -q bbr; then
        cat > "$BBR_CONF" << 'BBRCFG'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
BBRCFG
        sysctl --system >/dev/null 2>&1 || true
        say "$GREEN" "✓ BBR已开启"
    else
        say "$YELLOW" "△ 内核不支持BBR，跳过"
    fi
}

#=== 12. 配置测试 ==============================================================
test_configs() {
    nginx -t >/dev/null 2>&1 || return 1
    /usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json >/dev/null 2>&1 || return 1
    return 0
}

#=== 13. 启动服务 ============================================================
startServices() {
    say "$BLUE" ""; say "$BLUE" "测试配置..."
    if ! test_configs; then
        colorEcho "$RED" "配置测试失败，未启动服务"
        nginx -t 2>&1 | tail -3
        exit 1
    fi
    say "$BLUE" ""; say "$BLUE" "启动服务..."
    systemctl restart xray 2>/dev/null || true; systemctl restart nginx 2>/dev/null || true
    sleep 2
    if systemctl is-active --quiet xray && systemctl is-active --quiet nginx; then
        say "$GREEN" "✓ Xray + Nginx 运行中"
    else
        colorEcho "$RED" "✗ 服务启动失败，请检查日志"
        colorEcho "$YELLOW" "  journalctl -u xray --no-pager -n 20"
        colorEcho "$YELLOW" "  journalctl -u nginx --no-pager -n 20"
        exit 1
    fi
}

#=== 14. 保存信息 =============================================================
saveInfo() {
    IP=$(curl -s4m5 https://ip.gs || curl -s4m5 https://ifconfig.me || echo "unknown")
    mkdir -p /etc/huarun
    local swap_entry="null"
    [[ $SWAP_MADE -eq 1 ]] && swap_entry="\"${SWAP_FILE}\""
    cat > "${INFO_FILE}" << EOF
{
  "version": "${VERSION}",
  "domain": "${DOMAIN}",
  "port": 443,
  "uuid": "${UUID}",
  "protocol": "vmess",
  "network": "ws",
  "tls": "tls",
  "wsPath": "${WS_PATH}",
  "xrayPort": ${XRAY_PORT},
  "ip": "${IP}",
  "siteType": "${SITE_TYPE}",
  "assistant": false,
  "managedPaths": {
    "xrayConfig": "/usr/local/etc/xray/config.json",
    "nginxConfig": "/etc/nginx/conf.d/huarun.conf",
    "siteDir": "${SITE_DIR}",
    "templatesDir": "${TPL_DIR}",
    "certDir": "${CERT_DIR}",
    "cronFile": "${CRON_FILE}",
    "bbrConf": "${BBR_CONF}",
    "swapFile": ${swap_entry},
    "assistantDir": "${AI_HOME}",
    "assistantTemplateDir": "${AI_TPL}",
    "whitelist": "/usr/local/etc/xray/whitelist.txt",
    "tosFile": "/usr/local/etc/xray/TOS.txt"
  }
}
EOF
    chmod 600 "${INFO_FILE}"
}

#=== 15. AI 助手模板（钥匙有没有都先放好，补装时用） ==========================
installAssistantTemplate() {
    mkdir -p "$AI_TPL"; chmod 700 "$AI_TPL"

    # 给模型看的身份：只许用 exec 跑 huarun 子命令
    cat > "${AI_TPL}/AGENT.md" << 'AGENTEOF'
::ILANG::v5.0
::STATE{@SELF, role:"华润网络助手", owner:"本机主人", runtime:"PicoClaw"}
::GENE{tool_scope|conf:confirmed|scope:global}
  T:通过 exec 运行 huarun 管理命令；每次传 action=run 和 command。
  T:通过 read_file 阅读工作区 skills/huarun/SKILL.md 并按技能执行。
  A:运行任意 shell 或拼接管道、重定向、子命令⇒命令闸拒绝。
::GENE{repair|conf:confirmed|scope:global}
  T:主人说有问题时先运行 huarun doctor --json，按结果运行 huarun fix，再运行 huarun doctor --json 与 huarun status --json。
  T:需要连接信息时运行 huarun info --json，原样给出 vmess 字段并解释从剪贴板导入。
  T:问证书到期日时根据 cert_days 回答具体天数。
  A:仅服务器检查通过就声称用户手机已连通⇒说明仅服务器检查通过并请用户实际连接验证。
::GENE{boundaries|conf:confirmed|scope:global}
  T:添加或删除单个网站时按主人的明确请求运行 huarun whitelist add 或 remove。
  T:清空或重置白名单、卸载及修改助手由主人在 SSH 终端自行运行，助手无权调用。
  A:索要密码或 API Key、打印秘密文件、编造执行结果⇒停止该动作并据实说明。
::GENE{reply|conf:confirmed|scope:global}
  T:使用简体中文；先说具体结果，再用两三句话说明做了什么和仍需用户做什么。
AGENTEOF

    cat > "${AI_TPL}/SOUL.md" << 'SOULEOF'
::ILANG::v5.0
::GENE{service|conf:confirmed|scope:global}
  T:先根据真实工具结果行动，再用简体中文说明结果。
  T:保留主人的连接参数和白名单；只做已授权的管理操作。
  A:没有工具证据却说已经修好⇒撤回结论并检查。
SOULEOF

    mkdir -p "${AI_TPL}/skills/huarun"
    cat > "${AI_TPL}/skills/huarun/SKILL.md" << 'SKILLEOF'
---
name: huarun
description: 华润服务器网络服务的诊断、修复、连接信息、证书和网站白名单管理。
---
::ILANG::v5.0
::STATE{@SERVER, has:"Xray、Nginx、TLS、证书续期与网站白名单", command:"huarun"}
::STATE{@OWNER, role:"本机主人", input:"中文描述需求或故障"}
::GENE{diagnose|conf:confirmed|scope:global}
  T:运行 huarun doctor --json，逐项读取 checks 的 ok 和 hint。
  T:优先检查 xray、nginx、port443、配置、证书、cron、防火墙、域名解析、磁盘。
  T:dns 只证明域名可以解析，CDN 地址不同于源站属正常现象。
  A:没有故障证据时猜测客户端已损坏⇒报告已检查的服务器状态，再请主人提供客户端现象。
::GENE{repair|conf:confirmed|scope:global}
  T:发现可修的服务器故障时运行 huarun fix，再运行 huarun doctor --json 与 huarun status --json。
  T:fix 按顺序修复坏配置、放行端口、恢复续期任务、续签证书和启动服务。
  T:仍失败时运行 huarun logs 50，概括具体错误与下一步，不反复执行相同操作。
  A:检查只覆盖服务器就声称用户端已恢复⇒明确尚需用户导入节点并实际访问。
::GENE{connect|conf:confirmed|scope:global}
  T:运行 huarun info --json，把 vmess 字段整行给主人。
  T:手机用 Shadowrocket 或 v2rayNG，Windows 用 v2rayN，通过从剪贴板导入添加节点后开启连接。
  T:让主人访问白名单内的网站，例如 x.com，实际确认客户端连通。
::GENE{whitelist|conf:confirmed|scope:global}
  T:先运行 huarun whitelist list；按明确请求运行 huarun whitelist add example.com 或 huarun whitelist remove example.com。
  T:白名单是服务端放行规则，未列入的目标在隧道内被拒绝；不会替客户端自动设置直连。
  T:清空、重置白名单和卸载交给主人在 SSH 终端操作。
  A:使用 uninstall、assistant、whitelist clear 或 reset⇒命令闸拒绝。
::GENE{report|conf:confirmed|scope:global}
  T:所有结果对应实际工具输出；证书查询返回 cert_days 的具体天数。
  T:命令闸拒绝或 API 失败时据实说明，避免冒充已执行。
  T:只使用 huarun status、doctor、info、fix、logs、renew、update、version、whitelist list/add/remove 以及 free -m、df -h、uptime、date。
SKILLEOF

    # approve_tool 钩子：命令级白名单，fail-closed
    cat > "${AI_TPL}/gate.py" << 'GATEEOF'
#!/usr/bin/env python3
# 华润网络助手 助手的命令闸：只放行 huarun 子命令和几条只读命令；别的一律拒。
import sys, json, re

ALLOW = [
    re.compile(r"huarun (status|doctor|info)( --json)?"),
    re.compile(r"huarun (fix|renew|update|version)"),
    re.compile(r"huarun logs( [0-9]{1,3})?"),
    re.compile(r"huarun whitelist list"),
    re.compile(r"huarun whitelist (add|remove) [a-z0-9.-]{3,100}"),
    re.compile(r"free -m|df -h|uptime|date"),
]

def truthy(v):
    return v is True or str(v).lower() == "true"

def approve(p):
    if not isinstance(p, dict):
        return {"approved": False, "reason": "invalid request"}
    tool = p.get("tool")
    a = p.get("arguments") or {}
    if not isinstance(a, dict):
        return {"approved": False, "reason": "invalid arguments"}
    if tool == "read_file":
        return {"approved": True}
    if tool != "exec":
        return {"approved": False, "reason": "tool not allowed"}
    if a.get("action") != "run" or truthy(a.get("background")) or truthy(a.get("pty")) or a.get("cwd"):
        return {"approved": False, "reason": "only plain foreground run is allowed"}
    cmd = (a.get("command") or "").strip()
    if any(r.fullmatch(cmd) for r in ALLOW):
        return {"approved": True}
    return {"approved": False, "reason": "command not in huarun allowlist"}

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        m = json.loads(line)
    except Exception:
        continue
    i = m.get("id")
    if i is None:
        continue
    meth = m.get("method")
    p = m.get("params") or {}
    if meth == "hook.hello":
        r = {"ok": True}
    elif meth == "hook.approve_tool":
        r = approve(p)
    else:
        r = {"action": "continue"}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": i, "result": r}) + "\n")
    sys.stdout.flush()
GATEEOF
    chmod 0644 "${AI_TPL}/AGENT.md" "${AI_TPL}/SOUL.md" "${AI_TPL}/skills/huarun/SKILL.md" "${AI_TPL}/gate.py"
}

#=== 16. 装 AI 助手（有钥匙才装） ============================================
installAssistant() {
    [[ -n "$AI_KEY" && -f "$PICO_BIN_READY" ]] || { echo "助手安装前置条件未满足" >&2; return 1; }
    say "$BLUE" "安装 PicoClaw ${PICO_VERSION} 和华润运维技能..."
    mkdir -p /usr/local/lib/huarun
    install -m 0755 "$PICO_BIN_READY" /usr/local/lib/huarun/picoclaw
    setupAssistantHome "$AI_KEY"
    [[ -s "${AI_HOME}/config.json" && -s "${AI_HOME}/.security.yml" ]] || { echo "助手配置不完整，安装未完成" >&2; return 1; }
}

# 把钥匙和我们的文件装进助手目录（装机和 huarun assistant setup 共用）
setupAssistantHome() {
    local key="$1" ws="${AI_HOME}/workspace"
    export -n key AI_KEY
    mkdir -p "$AI_HOME"; chmod 700 "$AI_HOME"
    PICOCLAW_HOME="$AI_HOME" PICOCLAW_CONFIG="${AI_HOME}/config.json" /usr/local/lib/huarun/picoclaw onboard >/dev/null 2>&1 || true
    [[ -f "${AI_HOME}/config.json" ]] || { colorEcho "$RED" "助手初始化失败（没有 config.json）"; return 1; }
    mkdir -p "$ws/skills" "$ws/memory"
    mkdir -p "$ws/skills/huarun"
    cp "${AI_TPL}/AGENT.md" "$ws/AGENT.md"
    cp "${AI_TPL}/SOUL.md" "$ws/SOUL.md"
    cp "${AI_TPL}/skills/huarun/SKILL.md" "$ws/skills/huarun/SKILL.md"
    install -m 0755 "${AI_TPL}/gate.py" "${AI_HOME}/gate.py"
    rm -f "$ws/USER.md" "$ws/IDENTITY.md" "$ws/AGENTS.md" 2>/dev/null || true

    # 钥匙单独放，600
    umask 077
    printf 'model_list:\n  %s:\n    api_keys:\n      - "%s"\n' "$AI_MODEL" "$key" > "${AI_HOME}/.security.yml"
    umask 022
    chmod 600 "${AI_HOME}/.security.yml"

    # 配置：只留 exec + read_file，远程通道关，钩子当命令闸
    AI_HOME="$AI_HOME" WS="$ws" AI_MODEL="$AI_MODEL" AI_PROVIDER="$AI_PROVIDER" AI_API_BASE="$AI_API_BASE" python3 - << 'PYEOF'
import json, os
home = os.environ["AI_HOME"]; ws = os.environ["WS"]
p = os.path.join(home, "config.json")
c = json.load(open(p))
d = c.setdefault("agents", {}).setdefault("defaults", {})
d.update({"workspace": ws, "restrict_to_workspace": True, "allow_read_outside_workspace": False,
          "model_name": os.environ["AI_MODEL"], "max_tool_iterations": 20})
c["model_list"] = [{"model_name": os.environ["AI_MODEL"], "provider": os.environ["AI_PROVIDER"],
                    "model": os.environ["AI_MODEL"], "api_base": os.environ["AI_API_BASE"], "enabled": True}]
t = c.setdefault("tools", {})
t["filter_sensitive_data"] = True
t.setdefault("exec", {}).update({"enabled": True, "enable_deny_patterns": True, "allow_remote": False, "timeout_seconds": 300})
t.setdefault("read_file", {}).update({"enabled": True})
for name in ["write_file", "edit_file", "append_file", "list_dir", "load_image", "send_file", "send_tts", "message",
             "web", "web_fetch", "spawn", "spawn_status", "subagent", "skills", "find_skills", "install_skill",
             "mcp", "cron", "i2c", "spi", "serial"]:
    t.setdefault(name, {})
    if isinstance(t[name], dict):
        t[name]["enabled"] = False
c["hooks"] = {"enabled": True, "processes": {"ai_xray_gate": {"enabled": True, "transport": "stdio",
              "command": ["/usr/bin/python3", os.path.join(home, "gate.py")], "intercept": ["approve_tool"]}}}
c.setdefault("gateway", {})["log_level"] = "error"   # 模型调工具参数写错时的 WRN 不刷进对话
json.dump(c, open(p, "w"), indent=2, ensure_ascii=False)
PYEOF
    chmod 600 "${AI_HOME}/config.json"

    # info.json 记一笔
    if [[ -f "$INFO_FILE" ]]; then
        jq '.assistant = true' "$INFO_FILE" > "${INFO_FILE}.tmp" && mv "${INFO_FILE}.tmp" "$INFO_FILE" && chmod 600 "$INFO_FILE"
    fi
    say "$GREEN" "✓ AI 助手已装好：以后输入 huarun chat 跟它说话"
}

#=== 17. 输出信息 ============================================================
vmessLink() {
    local raw
    raw="{\"v\":\"2\",\"ps\":\"华润网络助手-${DOMAIN}\",\"add\":\"${DOMAIN}\",\"port\":\"443\",\"id\":\"${UUID}\",\"aid\":\"0\",\"net\":\"ws\",\"type\":\"none\",\"host\":\"${DOMAIN}\",\"path\":\"${WS_PATH}\",\"tls\":\"tls\"}"
    echo "vmess://$(echo -n "$raw" | base64 -w 0)"
}

showInfo() {
    local link
    link=$(vmessLink)
    if [[ $OPT_JSON -eq 1 ]]; then
        jq -n --arg v "$VERSION" --arg d "$DOMAIN" --arg u "$UUID" --arg p "$WS_PATH" --arg l "$link" --argjson a "$([[ -n "$AI_KEY" && -f "${AI_HOME}/config.json" ]] && echo true || echo false)" \
            '{version:$v, domain:$d, port:443, protocol:"vmess", network:"ws", tls:"tls", uuid:$u, wsPath:$p, vmess:$l, assistant:$a}'
        return 0
    fi
    echo ""; echo -e "${GREEN}========================================${PLAIN}"
    echo -e "${GREEN}华润网络助手 安装完成 v${VERSION}${PLAIN}"
    echo -e "${GREEN}========================================${PLAIN}"
    echo ""
    echo -e "  域名：      ${RED}${DOMAIN}${PLAIN}"
    echo -e "  端口：      ${RED}443${PLAIN}"
    echo -e "  UUID：      ${RED}${UUID}${PLAIN}"
    echo -e "  协议：      ${RED}VMESS + WS + TLS${PLAIN}"
    echo -e "  WS路径：    ${RED}${WS_PATH}${PLAIN}"
    echo -e "  站点：    ${RED}https://${DOMAIN}${PLAIN}"
    echo ""
    echo -e "${BLUE}  VMess链接：${PLAIN}"
    echo -e "${RED}  ${link}${PLAIN}"
    echo ""
    echo -e "  客户端导入说明：${BLUE}${DOCS_URL}${PLAIN}"
    echo ""
    echo -e "  可选：Cloudflare开启橙色云朵(Proxied)"
    echo -e "        SSL模式选Full(strict)"
    echo ""
    echo -e "  管理命令：${BLUE}huarun${PLAIN}"
    echo -e "  证书自动续期：${BLUE}${CRON_FILE}${PLAIN}（每天 03:23 检查）"
    if [[ -f "${AI_HOME}/config.json" ]]; then
        echo -e "  AI 助手：   ${BLUE}huarun chat${PLAIN}（出了问题跟它说一句）"
    fi
    echo ""
    echo -e "  ${YELLOW}默认已启用跨境出海白名单（$(wc -w <<< "$DEFAULT_DOMAINS") 个根域名：谷歌与 YouTube、Meta、TikTok、X、亚马逊、eBay、Shopify、PayPal 等）${PLAIN}"
    echo -e "  ${YELLOW}输入 huarun 进入管理菜单修改白名单${PLAIN}"
    echo -e "${GREEN}========================================${PLAIN}"
}

#=== 18. 安装管理命令 ========================================================
installManager() {
    cat > /usr/local/bin/huarun << 'MGRSCRIPT'
#!/bin/bash
VERSION="1.0.0"
INFO_FILE="/etc/huarun/info.json"
SITE_DIR="/usr/share/nginx/huarun"
TPL_DIR="/usr/share/nginx/huarun-templates"
CERT_DIR="/etc/nginx/ssl/huarun"
ACME_HOME="/etc/huarun/acme"
ACME_BIN="/usr/local/lib/huarun/acme.sh"
XRAY_BIN="/usr/local/bin/xray"
XRAY_CFG="/usr/local/etc/xray/config.json"
WHITELIST="/usr/local/etc/xray/whitelist.txt"
CRON_FILE="/etc/cron.d/huarun-acme"
AI_HOME="/etc/huarun/assistant"
AI_TPL="/etc/huarun/assistant-template"
AI_MODEL="deepseek-flash"
AI_PROVIDER="deepseek"
AI_API_BASE="https://api.deepseek.com/v1"
DEFAULT_DOMAINS="__DEFAULT_DOMAINS__"

RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[36m"; PLAIN="\033[0m"
colorEcho() { echo -e "${1}${*:2}${PLAIN}"; }
info_get() { jq -r "$1 // empty" "$INFO_FILE" 2>/dev/null; }

show_menu() {
    echo ""; echo -e "${BLUE}华润网络助手 管理菜单 v${VERSION}${PLAIN}"; echo ""
    echo "  1) 查看连接信息"
    echo "  2) 重新生成站点"
    echo "  3) 更新Xray内核"
    echo "  4) 重启服务"
    echo "  5) 查看日志"
    echo "  6) 查看状态"
    echo "  7) 白名单管理"
    echo "  8) 卸载"
    echo "  9) 手动续期证书"
    echo " 10) 体检并自动修复"
    echo " 11) 跟 AI 助手说话"
    echo "  0) 退出"
    echo ""
    read -r -p "请选择[0-11]: " choice

    case $choice in
        1) show_info ;;
        2) render_site && colorEcho "$GREEN" "✓ 站点已刷新" ;;
        3) update_xray ;;
        4) restart_services ;;
        5) view_logs 30 ;;
        6) show_status ;;
        7) whitelist_menu ;;
        8) uninstall ;;
        9) renew_cert ;;
        10) do_fix ;;
        11) chat ;;
        0) exit 0 ;;
        *) colorEcho "$RED" "无效选项" && show_menu ;;
    esac
}

vmess_link() {
    local d u p raw
    d=$(info_get .domain); u=$(info_get .uuid); p=$(info_get .wsPath)
    raw="{\"v\":\"2\",\"ps\":\"华润网络助手-${d}\",\"add\":\"${d}\",\"port\":\"443\",\"id\":\"${u}\",\"aid\":\"0\",\"net\":\"ws\",\"type\":\"none\",\"host\":\"${d}\",\"path\":\"${p}\",\"tls\":\"tls\"}"
    echo "vmess://$(echo -n "$raw" | base64 -w 0)"
}

show_info() {
    [[ -f "$INFO_FILE" ]] || { colorEcho "$RED" "未安装华润网络助手"; return 1; }
    if [[ "${1:-}" == "--json" ]]; then
        jq --arg l "$(vmess_link)" '{domain, port, protocol, network, tls, uuid, wsPath, vmess:$l, assistant}' "$INFO_FILE"
        return 0
    fi
    echo ""; colorEcho "$BLUE" "连接信息："
    echo -e "  域名:   ${GREEN}$(info_get .domain)${PLAIN}"
    echo -e "  端口:   ${GREEN}443${PLAIN}"
    echo -e "  UUID:   ${GREEN}$(info_get .uuid)${PLAIN}"
    echo -e "  WS路径: ${GREEN}$(info_get .wsPath)${PLAIN}"
    echo -e "  VMess:  ${GREEN}$(vmess_link)${PLAIN}"
}

render_site() {
    local site_type title build
    site_type=$(jq -r '.siteType // "1"' "$INFO_FILE" 2>/dev/null || echo "1")
    mkdir -p "$SITE_DIR"
    if [[ "$site_type" == "4" ]] || [[ ! -f "${TPL_DIR}/${site_type}.html" ]]; then
        echo '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Welcome</title></head><body></body></html>' > "${SITE_DIR}/index.html"
        return 0
    fi
    local titles=()
    case "$site_type" in
        1) titles=("Developer Documentation" "API Reference" "Protocol Documentation" "Integration Guide" "Platform Docs") ;;
        2) titles=("Encryption Toolkit" "Cipher and Hash Utilities" "Crypto Tools" "Security Utilities" "Digest Workbench") ;;
        3) titles=("Student Resources" "Campus Deals Directory" "Student Discounts Hub" "Scholar Perks" "Campus Savings") ;;
    esac
    title="${titles[$((RANDOM % ${#titles[@]}))]}"
    build=$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' | cut -c1-8)
    sed -e "s/{{TITLE}}/${title}/g" -e "s/{{BUILD}}/${build}/g" -e "s/{{YEAR}}/$(date +%Y)/g" \
        "${TPL_DIR}/${site_type}.html" > "${SITE_DIR}/index.html"
}

update_xray() {
    colorEcho "$BLUE" "检查Xray更新..."
    XRAY_URL="https://raw.githubusercontent.com/XTLS/Xray-install/e741a4f56d368afbb9e5be3361b40c4552d3710d/install-release.sh"
    XRAY_SHA="7f70c95f6b418da8b4f4883343d602964915e28748993870fd554383afdbe555"
    tmp_x=$(mktemp)
    curl -fsSL "$XRAY_URL" -o "$tmp_x" || { colorEcho "$RED" "下载失败"; rm -f "$tmp_x"; return 1; }
    echo "${XRAY_SHA}  ${tmp_x}" | sha256sum -c - >/dev/null || {
        colorEcho "$RED" "Xray校验失败"; rm -f "$tmp_x"; return 1
    }
    if ! bash "$tmp_x" install >/dev/null 2>&1; then
        rm -f "$tmp_x"; colorEcho "$RED" "✗ Xray 更新失败，未报告成功"; return 1
    fi
    rm -f "$tmp_x"
    "$XRAY_BIN" run -test -config "$XRAY_CFG" >/dev/null 2>&1 || { colorEcho "$RED" "✗ 更新后配置校验失败"; return 1; }
    systemctl restart xray && systemctl is-active --quiet xray || { colorEcho "$RED" "✗ 更新后 Xray 未运行"; return 1; }
    colorEcho "$GREEN" "✓ Xray已更新到 $("$XRAY_BIN" version 2>/dev/null | head -1 | awk '{print $2}')"
}

restart_services() {
    nginx -t >/dev/null 2>&1 || { colorEcho "$RED" "nginx配置测试失败"; nginx -t 2>&1 | tail -2; return 1; }
    "$XRAY_BIN" run -test -config "$XRAY_CFG" >/dev/null 2>&1 || { colorEcho "$RED" "Xray 配置测试失败"; return 1; }
    systemctl restart xray && systemctl restart nginx && systemctl is-active --quiet xray && systemctl is-active --quiet nginx || { colorEcho "$RED" "✗ 服务重启失败"; return 1; }
    colorEcho "$GREEN" "✓ 服务已重启"
}

view_logs() {
    local n="${1:-30}"
    [[ "$n" =~ ^[0-9]+$ ]] || n=30
    echo ""; colorEcho "$BLUE" "Xray日志（最近 ${n} 行）："
    journalctl -u xray --no-pager -n "$n" 2>/dev/null || tail -n "$n" /var/log/xray/error.log 2>/dev/null
    echo ""; colorEcho "$BLUE" "Nginx错误日志（最近 10 行）："
    tail -10 /var/log/nginx/error.log 2>/dev/null || echo "无日志"
}

cert_days() {
    local enddate
    [[ -f "${CERT_DIR}/fullchain.cer" ]] || { echo -1; return; }
    enddate=$(openssl x509 -enddate -noout -in "${CERT_DIR}/fullchain.cer" 2>/dev/null | cut -d= -f2)
    [[ -n "$enddate" ]] || { echo -1; return; }
    echo $(( ( $(date -d "$enddate" +%s) - $(date +%s) ) / 86400 ))
}

# 体检：每项 ok/false + 提示；--json 给助手用
run_doctor() {
    local json="${1:-}" d days xray_ok nginx_ok p443 cron_ok cert_ok xcfg_ok ncfg_ok fw_ok dns_ok disk_ok mem_avail swap_ok
    d=$(info_get .domain)
    systemctl is-active --quiet xray && xray_ok=true || xray_ok=false
    systemctl is-active --quiet nginx && nginx_ok=true || nginx_ok=false
    ss -tlnp 2>/dev/null | grep -q ':443 ' && p443=true || p443=false
    [[ -f "$CRON_FILE" ]] && grep -q 'acme.sh --cron' "$CRON_FILE" && cron_ok=true || cron_ok=false
    days=$(cert_days); [[ $days -ge 15 ]] && cert_ok=true || cert_ok=false
    "$XRAY_BIN" run -test -config "$XRAY_CFG" >/dev/null 2>&1 && xcfg_ok=true || xcfg_ok=false
    nginx -t >/dev/null 2>&1 && ncfg_ok=true || ncfg_ok=false
    fw_ok=true
    if systemctl is-active --quiet firewalld 2>/dev/null; then firewall-cmd --list-services 2>/dev/null | grep -q https || fw_ok=false; fi
    if which ufw &>/dev/null && ufw status 2>/dev/null | grep -q '^Status: active'; then ufw status 2>/dev/null | grep -qE '^443(/tcp)?\s+ALLOW' || fw_ok=false; fi
    local dnsip
    dnsip=$(getent ahosts "$d" 2>/dev/null | awk '{print $1; exit}')
    [[ -n "$dnsip" ]] && dns_ok=true || dns_ok=false
    disk_ok=true; [[ $(df -P / | awk 'NR==2{print $5}' | tr -d %) -ge 95 ]] && disk_ok=false
    mem_avail=$(awk '/MemAvailable/{printf "%d", $2/1024}' /proc/meminfo)
    swapon --show 2>/dev/null | grep -q . && swap_ok=true || swap_ok=false
    if [[ "$json" == "--json" ]]; then
        jq -n --arg d "$d" --argjson days "$days" --argjson mem "$mem_avail" \
            --argjson xray "$xray_ok" --argjson nginx "$nginx_ok" --argjson p443 "$p443" --argjson cron "$cron_ok" --argjson cert "$cert_ok" \
            --argjson xcfg "$xcfg_ok" --argjson ncfg "$ncfg_ok" --argjson fw "$fw_ok" --argjson dns "$dns_ok" --argjson disk "$disk_ok" --argjson swap "$swap_ok" \
            '{domain:$d, scope:"server", client_connectivity:"not_tested", cert_days:$days, mem_available_mb:$mem, checks:{
                xray:{ok:$xray, hint:"xray 服务没在跑，fix 会重启它"},
                nginx:{ok:$nginx, hint:"nginx 没在跑，多半是配置坏了或 80/443 被占，fix 会重建配置并重启"},
                port443:{ok:$p443, hint:"443 没在监听"},
                xray_config:{ok:$xcfg, hint:"xray 配置通不过校验，fix 会按白名单重建路由"},
                nginx_config:{ok:$ncfg, hint:"nginx 配置通不过校验，fix 会重建"},
                cert:{ok:$cert, hint:"证书过期或 15 天内到期，fix 会续签"},
                cron:{ok:$cron, hint:"续期定时任务不在，fix 会补上"},
                firewall:{ok:$fw, hint:"防火墙没放行 443，fix 会放行"},
                dns:{ok:$dns, hint:"域名无法解析，请检查 DNS；CDN IP 与源站不同不会据此报错"},
                disk:{ok:$disk, hint:"磁盘快满了"},
                swap:{ok:$swap, hint:"没有 swap（内存小的机器建议有）"}
            }, all_ok:($xray and $nginx and $p443 and $xcfg and $ncfg and $cert and $cron and $fw and $dns and $disk)}'
        return 0
    fi
    echo ""; colorEcho "$BLUE" "体检："
    local item
    for item in "xray:$xray_ok:xray 服务" "nginx:$nginx_ok:nginx 服务" "443:$p443:443 端口监听" "xray_config:$xcfg_ok:xray 配置校验" "nginx_config:$ncfg_ok:nginx 配置校验" \
                "cert:$cert_ok:证书（剩 ${days} 天）" "cron:$cron_ok:续期定时任务" "firewall:$fw_ok:防火墙放行 443" "dns:$dns_ok:域名可解析" "disk:$disk_ok:磁盘空间" "swap:$swap_ok:swap"; do
        local v t; v=$(echo "$item" | cut -d: -f2); t=${item#*:*:}
        [[ "$v" == "true" ]] && echo -e "  ${GREEN}✓${PLAIN} $t" || echo -e "  ${RED}✗${PLAIN} $t"
    done
    echo "  可用内存 ${mem_avail}MB"
}

# 修：按顺序把能修的都修了，每步说做了什么
do_fix() {
    local d p port u days fixed=0
    [[ -f "$INFO_FILE" ]] || { colorEcho "$RED" "未安装华润网络助手"; return 1; }
    d=$(info_get .domain); p=$(info_get .wsPath); port=$(info_get .xrayPort); u=$(info_get .uuid)
    echo ""; colorEcho "$BLUE" "开始修..."
    # 1. nginx 配置
    if ! nginx -t >/dev/null 2>&1; then
        if [[ -n "$d" && -n "$p" && -n "$port" ]]; then
            mkdir -p /etc/nginx/conf.d
            local l6="" l680=""; [[ -f /proc/net/if_inet6 ]] && l6="    listen [::]:443 ssl http2;" && l680="    listen [::]:80;"
            cat > /etc/nginx/conf.d/huarun.conf << NEOF
server {
    listen 443 ssl http2;
${l6}
    server_name ${d};
    ssl_certificate ${CERT_DIR}/fullchain.cer;
    ssl_certificate_key ${CERT_DIR}/${d}.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    location ${p} {
        proxy_redirect off;
        proxy_pass http://127.0.0.1:${port};
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
    location / { root ${SITE_DIR}; index index.html; try_files \$uri \$uri/ =404; }
}
server {
    listen 80;
${l680}
    server_name ${d};
    return 301 https://\$host\$request_uri;
}
NEOF
            nginx -t >/dev/null 2>&1 && { echo "  ✓ 重建了 nginx 配置"; fixed=1; } || echo "  ✗ nginx 配置重建后仍通不过：$(nginx -t 2>&1 | tail -1)"
        fi
    fi
    # 2. xray 配置
    if ! "$XRAY_BIN" run -test -config "$XRAY_CFG" >/dev/null 2>&1; then
        if [[ -n "$u" && -n "$p" && -n "$port" ]]; then
            cat > "$XRAY_CFG" << XEOF
{"log":{"loglevel":"warning","access":"/var/log/xray/access.log","error":"/var/log/xray/error.log"},
 "inbounds":[{"tag":"vmess-ws","port":${port},"listen":"127.0.0.1","protocol":"vmess","settings":{"clients":[{"id":"${u}"}]},
   "streamSettings":{"network":"ws","wsSettings":{"path":"${p}"}},"sniffing":{"enabled":true,"destOverride":["http","tls","quic"],"routeOnly":true}}],
 "outbounds":[{"protocol":"freedom","tag":"direct"},{"protocol":"blackhole","tag":"blocked"}],
 "routing":{"domainStrategy":"IPIfNonMatch","rules":[{"type":"field","port":"0-65535","outboundTag":"blocked"}]}}
XEOF
            [[ -f "$WHITELIST" ]] || echo "$DEFAULT_DOMAINS" | tr ' ' '\n' > "$WHITELIST"
            rebuild_routing >/dev/null 2>&1 && { echo "  ✓ 重建了 xray 配置和白名单路由"; fixed=1; } || echo "  ✗ xray 配置重建失败"
        fi
    fi
    # 3. 防火墙
    if systemctl is-active --quiet firewalld 2>/dev/null && ! firewall-cmd --list-services 2>/dev/null | grep -q https; then
        firewall-cmd --permanent --add-service=http >/dev/null 2>&1; firewall-cmd --permanent --add-service=https >/dev/null 2>&1; firewall-cmd --reload >/dev/null 2>&1
        echo "  ✓ firewalld 放行了 80/443"; fixed=1
    fi
    if which ufw &>/dev/null && ufw status 2>/dev/null | grep -q '^Status: active' && ! ufw status 2>/dev/null | grep -qE '^443(/tcp)?\s+ALLOW'; then
        ufw allow 80/tcp >/dev/null 2>&1; ufw allow 443/tcp >/dev/null 2>&1
        echo "  ✓ ufw 放行了 80/443"; fixed=1
    fi
    # 4. 续期任务
    if ! { [[ -f "$CRON_FILE" ]] && grep -q 'acme.sh --cron' "$CRON_FILE"; }; then
        printf 'SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n23 3 * * * root %s --cron --home %s > /dev/null 2>&1\n' "$ACME_BIN" "$ACME_HOME" > "$CRON_FILE"
        chmod 644 "$CRON_FILE"; echo "  ✓ 补上了续期定时任务"; fixed=1
    fi
    # 5. 证书
    days=$(cert_days)
    if [[ $days -lt 15 ]]; then
        echo "  证书剩 ${days} 天，续签..."
        if "$ACME_BIN" --home "$ACME_HOME" --renew -d "$d" --ecc --force >/dev/null 2>&1; then echo "  ✓ 证书续签成功"; fixed=1; else echo "  ✗ 证书续签失败（看 huarun logs，常见是 80 端口不通或域名没解析到本机）"; fi
    fi
    # 6. 服务
    systemctl enable xray nginx >/dev/null 2>&1 || true
    if ! systemctl is-active --quiet xray; then systemctl restart xray 2>/dev/null && { echo "  ✓ 重启了 xray"; fixed=1; } || echo "  ✗ xray 起不来"; fi
    if ! systemctl is-active --quiet nginx; then systemctl restart nginx 2>/dev/null && { echo "  ✓ 重启了 nginx"; fixed=1; } || echo "  ✗ nginx 起不来：$(journalctl -u nginx --no-pager -n 2 2>/dev/null | tail -1)"; fi
    [[ $fixed -eq 0 ]] && echo "  没有发现要修的地方"
    sleep 1
    run_doctor
    local result
    result=$(run_doctor --json) || return 1
    if ! jq -e '.all_ok == true' >/dev/null <<< "$result"; then
        colorEcho "$RED" "✗ 仍有服务器检查未通过，请查看 huarun doctor --json"; return 1
    fi
    colorEcho "$GREEN" "✓ 服务器检查通过；请在客户端实际连接验证"
}

show_status() {
    if [[ "${1:-}" == "--json" ]]; then
        local days; days=$(cert_days)
        jq -n --arg v "$VERSION" --arg x "$(systemctl is-active xray 2>/dev/null)" --arg n "$(systemctl is-active nginx 2>/dev/null)" \
            --argjson p "$(ss -tlnp 2>/dev/null | grep -q ':443 ' && echo true || echo false)" --argjson days "$days" \
            --argjson cron "$([[ -f "$CRON_FILE" ]] && echo true || echo false)" --argjson a "$([[ -f "${AI_HOME}/config.json" ]] && echo true || echo false)" \
            '{version:$v, xray:$x, nginx:$n, port443:$p, cert_days:$days, renew_cron:$cron, assistant:$a}'
        return 0
    fi
    echo ""; echo -n "Xray: "
    systemctl is-active --quiet xray && echo -e "${GREEN}运行中${PLAIN}" || echo -e "${RED}未运行${PLAIN}"
    echo -n "Nginx: "
    systemctl is-active --quiet nginx && echo -e "${GREEN}运行中${PLAIN}" || echo -e "${RED}未运行${PLAIN}"
    echo -n "443端口: "
    ss -tlnp | grep -q ':443 ' && echo -e "${GREEN}监听中${PLAIN}" || echo -e "${RED}未监听${PLAIN}"
    echo -n "证书到期: "
    local days; days=$(cert_days)
    if [[ $days -lt 0 ]]; then echo -e "${RED}证书文件不存在或读不出${PLAIN}"
    elif [[ $days -lt 15 ]]; then echo -e "${RED}剩 ${days} 天${PLAIN}"
    else echo -e "${GREEN}剩 ${days} 天${PLAIN}"; fi
    echo -n "自动续期: "
    [[ -f "$CRON_FILE" ]] && echo -e "${GREEN}已登记${PLAIN}" || echo -e "${RED}未登记（运行 huarun fix）${PLAIN}"
    echo -n "AI 助手: "
    [[ -f "${AI_HOME}/config.json" ]] && echo -e "${GREEN}已装（huarun chat）${PLAIN}" || echo -e "${YELLOW}未装（huarun assistant setup）${PLAIN}"
}

renew_cert() {
    local domain
    domain=$(info_get .domain)
    [[ -n "$domain" ]] || { colorEcho "$RED" "读不到域名"; return 1; }
    colorEcho "$BLUE" "续期证书 ${domain}..."
    if "$ACME_BIN" --home "$ACME_HOME" --renew -d "$domain" --ecc --force; then
        systemctl is-active --quiet nginx && systemctl reload nginx
        colorEcho "$GREEN" "✓ 续期完成，剩 $(cert_days) 天"
    else
        colorEcho "$RED" "✗ 续期失败，看上面的报错"
        return 1
    fi
}

# ---- AI 助手 ----
chat() {
    if [[ ! -f "${AI_HOME}/config.json" || ! -x /usr/local/lib/huarun/picoclaw ]]; then
        colorEcho "$YELLOW" "还没装 AI 助手。运行 huarun assistant setup 装一个（要一把 DeepSeek 钥匙）。"
        return 1
    fi
    echo -e "${BLUE}跟助手说话：有问题直接说，比如「手机连不上了」。输入 exit 退出。${PLAIN}"
    cd "${AI_HOME}/workspace" 2>/dev/null || true
    unset HUARUN_API_KEY AI_KEY SETUP_KEY
    PICOCLAW_HOME="$AI_HOME" PICOCLAW_CONFIG="${AI_HOME}/config.json" PICOCLAW_LOG_LEVEL=error exec /usr/local/lib/huarun/picoclaw agent "$@"
}

assistant_cmd() {
    case "${1:-}" in
        setup)
            local key="${HUARUN_API_KEY:-}"
            export -n key
            unset HUARUN_API_KEY
            if [[ -z "$key" ]]; then
                echo "助手用你自己的 DeepSeek 钥匙：platform.deepseek.com 注册，充 10 块，复制 API key。"
                read -r -s -p "把钥匙贴在这里（不回显）: " key; echo ""
            fi
            [[ "$key" =~ ^sk-[A-Za-z0-9_-]{8,}$ ]] || { colorEcho "$RED" "Key 格式不正确"; return 1; }
            local code; code=$(printf 'header = "Authorization: Bearer %s"\n' "$key" | curl -s -o /dev/null -w '%{http_code}' --max-time 20 --config - "${AI_API_BASE}/models" || true)
            [[ "$code" == "200" ]] || { colorEcho "$RED" "钥匙不能用（HTTP ${code}）"; return 1; }
            [[ -x /usr/local/lib/huarun/picoclaw ]] || { colorEcho "$RED" "picoclaw 没装缺失，请根据 apps/server 文档恢复助手，不要覆盖重装网络。"; return 1; }
            [[ -d "$AI_TPL" ]] || { colorEcho "$RED" "助手模板目录不在：$AI_TPL"; return 1; }
            SETUP_KEY="$key" bash -c '
                set -e
                setup_key="$SETUP_KEY"; export -n setup_key; unset SETUP_KEY
                AI_HOME="'"$AI_HOME"'"; AI_TPL="'"$AI_TPL"'"; AI_MODEL="'"$AI_MODEL"'"; AI_PROVIDER="'"$AI_PROVIDER"'"; AI_API_BASE="'"$AI_API_BASE"'"; INFO_FILE="'"$INFO_FILE"'"
                ws="${AI_HOME}/workspace"
                mkdir -p "$AI_HOME"; chmod 700 "$AI_HOME"
                PICOCLAW_HOME="$AI_HOME" PICOCLAW_CONFIG="${AI_HOME}/config.json" /usr/local/lib/huarun/picoclaw onboard >/dev/null 2>&1 || true
                [[ -f "${AI_HOME}/config.json" ]]
                mkdir -p "$ws/skills" "$ws/memory"; mkdir -p "$ws/skills/huarun"
                cp "${AI_TPL}/AGENT.md" "$ws/AGENT.md"; cp "${AI_TPL}/SOUL.md" "$ws/SOUL.md"; cp "${AI_TPL}/skills/huarun/SKILL.md" "$ws/skills/huarun/SKILL.md"
                install -m 0755 "${AI_TPL}/gate.py" "${AI_HOME}/gate.py"; rm -f "$ws/USER.md" "$ws/IDENTITY.md" "$ws/AGENTS.md"
                umask 077; printf "model_list:\n  %s:\n    api_keys:\n      - \"%s\"\n" "$AI_MODEL" "$setup_key" > "${AI_HOME}/.security.yml"; chmod 600 "${AI_HOME}/.security.yml"
                unset setup_key
                AI_HOME="$AI_HOME" WS="$ws" AI_MODEL="$AI_MODEL" AI_PROVIDER="$AI_PROVIDER" AI_API_BASE="$AI_API_BASE" python3 - <<PY
import json, os
home=os.environ["AI_HOME"]; ws=os.environ["WS"]; p=os.path.join(home,"config.json"); c=json.load(open(p))
d=c.setdefault("agents",{}).setdefault("defaults",{})
d.update({"workspace":ws,"restrict_to_workspace":True,"allow_read_outside_workspace":False,"model_name":os.environ["AI_MODEL"],"max_tool_iterations":20})
c["model_list"]=[{"model_name":os.environ["AI_MODEL"],"provider":os.environ["AI_PROVIDER"],"model":os.environ["AI_MODEL"],"api_base":os.environ["AI_API_BASE"],"enabled":True}]
t=c.setdefault("tools",{}); t["filter_sensitive_data"]=True
t.setdefault("exec",{}).update({"enabled":True,"enable_deny_patterns":True,"allow_remote":False,"timeout_seconds":300}); t.setdefault("read_file",{}).update({"enabled":True})
for n in ["write_file","edit_file","append_file","list_dir","load_image","send_file","send_tts","message","web","web_fetch","spawn","spawn_status","subagent","skills","find_skills","install_skill","mcp","cron","i2c","spi","serial"]:
    t.setdefault(n,{})
    if isinstance(t[n],dict): t[n]["enabled"]=False
c["hooks"]={"enabled":True,"processes":{"ai_xray_gate":{"enabled":True,"transport":"stdio","command":["/usr/bin/python3",os.path.join(home,"gate.py")],"intercept":["approve_tool"]}}}
c.setdefault("gateway",{})["log_level"]="error"
json.dump(c,open(p,"w"),indent=2,ensure_ascii=False)
PY
                chmod 600 "${AI_HOME}/config.json"
                [[ -f "$INFO_FILE" ]] && jq ".assistant = true" "$INFO_FILE" > "${INFO_FILE}.tmp" && mv "${INFO_FILE}.tmp" "$INFO_FILE" && chmod 600 "$INFO_FILE"
            ' && colorEcho "$GREEN" "✓ 助手装好了：huarun chat" || { colorEcho "$RED" "✗ 助手安装失败"; return 1; }
            ;;
        remove)
            require_terminal || return 1
            read -r -p "移除助手会删除其配置与 Key，输入 YES 确认: " confirm
            [[ "$confirm" == "YES" ]] || { echo "已取消"; return 1; }
            rm -rf "$AI_HOME"; [[ -f "$INFO_FILE" ]] && jq '.assistant = false' "$INFO_FILE" > "${INFO_FILE}.tmp" && mv "${INFO_FILE}.tmp" "$INFO_FILE" && chmod 600 "$INFO_FILE"
            colorEcho "$GREEN" "✓ 助手已移除（picoclaw 二进制保留）" ;;
        *) echo "用法: huarun assistant setup|remove" ;;
    esac
}

require_terminal() {
    [[ -t 0 ]] || { colorEcho "$RED" "此操作请由主人在 SSH 交互终端执行。"; return 1; }
}

uninstall() {
    require_terminal || return 1
    if [[ "${1:-}" != "--yes" ]]; then
        echo ""; colorEcho "$YELLOW" "确认卸载华润网络助手? [y/N]"
        read -r -p "" confirm
        [[ "$confirm" != "y" ]] && [[ "$confirm" != "Y" ]] && return
    fi
    if [[ -f "$INFO_FILE" ]]; then
        local XCFG NCFG SDIR TDIR CDIR CRONF BBRF SWAPF ADIR ATPL WL TOSF
        XCFG=$(info_get .managedPaths.xrayConfig); NCFG=$(info_get .managedPaths.nginxConfig)
        SDIR=$(info_get .managedPaths.siteDir); TDIR=$(info_get .managedPaths.templatesDir)
        CDIR=$(info_get .managedPaths.certDir); CRONF=$(info_get .managedPaths.cronFile); BBRF=$(info_get .managedPaths.bbrConf)
        SWAPF=$(info_get .managedPaths.swapFile); ADIR=$(info_get .managedPaths.assistantDir); ATPL=$(info_get .managedPaths.assistantTemplateDir)
        WL=$(info_get .managedPaths.whitelist); TOSF=$(info_get .managedPaths.tosFile)
        systemctl stop xray 2>/dev/null || true
        rm -f "$XCFG" "$NCFG" "$WL" "$TOSF" "$CRONF" "$BBRF"
        [[ -n "$SDIR" ]] && rm -rf "$SDIR"
        [[ -n "$TDIR" ]] && rm -rf "$TDIR"
        [[ -n "$CDIR" ]] && rm -rf "$CDIR"
        [[ -n "$ADIR" ]] && rm -rf "$ADIR"
        [[ -n "$ATPL" ]] && rm -rf "$ATPL"
        if [[ -n "$SWAPF" && "$SWAPF" != "null" && -f "$SWAPF" ]]; then
            swapoff "$SWAPF" 2>/dev/null || true; sed -i "\#^${SWAPF} #d" /etc/fstab 2>/dev/null || true; rm -f "$SWAPF"
        fi
        rm -rf /etc/huarun
        systemctl reload nginx 2>/dev/null || true
    fi
    rm -f /usr/local/bin/huarun /usr/local/lib/huarun/picoclaw
    colorEcho "$GREEN" "✓ 卸载完成（Xray 内核、nginx、acme.sh 本身未删除）"
}

rebuild_routing() {
    local tmp domains backup
    tmp=$(mktemp --suffix=.json)
    backup=$(mktemp --suffix=.json)
    cp "$XRAY_CFG" "$backup" || { rm -f "$tmp" "$backup"; return 1; }
    domains=$(grep -vE '^\s*(#|$)' "$WHITELIST" 2>/dev/null | jq -R -s 'split("\n") | map(select(length > 0)) | map("domain:" + .)')
    [[ -z "$domains" ]] && domains='[]'
    if jq -e --argjson d "$domains" '
        .routing = (if ($d | length) > 0 then
            {domainStrategy: "IPIfNonMatch",
             rules: [{type: "field", domain: $d, outboundTag: "direct"},
                     {type: "field", port: "0-65535", outboundTag: "blocked"}]}
        else
            {domainStrategy: "IPIfNonMatch",
             rules: [{type: "field", port: "0-65535", outboundTag: "blocked"}]}
        end)' "$XRAY_CFG" > "$tmp" 2>/dev/null \
       && "$XRAY_BIN" run -test -format json -config "$tmp" >/dev/null 2>&1; then
        if install -m 0644 "$tmp" "$XRAY_CFG" && systemctl restart xray 2>/dev/null && systemctl is-active --quiet xray; then
            rm -f "$tmp" "$backup"; return 0
        fi
        install -m 0644 "$backup" "$XRAY_CFG"
        systemctl restart xray >/dev/null 2>&1 || true
        rm -f "$tmp" "$backup"
        colorEcho "$RED" "✗ 新路由启动失败，已恢复原配置"; return 1
    fi
    rm -f "$tmp" "$backup"
    colorEcho "$RED" "✗ 路由配置生成或校验失败，原配置未动"
    return 1
}

normalize_domain() {
    echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's#^[a-z]+://##; s#/.*$##; s#:[0-9]+$##; s#^www\.##'
}
valid_domain() {
    echo "$1" | grep -qE '^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}$'
}

# Commit whitelist and routing together; failed validation/restart rolls both back.
commit_whitelist() {
    local candidate="$1" backup
    backup=$(mktemp)
    if [[ -f "$WHITELIST" ]]; then cp "$WHITELIST" "$backup" || { rm -f "$backup" "$candidate"; return 1; }; fi
    if install -m 0600 "$candidate" "$WHITELIST" && rebuild_routing; then
        rm -f "$backup" "$candidate"; return 0
    fi
    install -m 0600 "$backup" "$WHITELIST"
    rm -f "$backup" "$candidate"
    colorEcho "$YELLOW" "白名单修改失败，已恢复原白名单"
    return 1
}

wl_add() {
    local d candidate
    d=$(normalize_domain "$1")
    valid_domain "$d" || { colorEcho "$RED" "域名格式不对，只要主域名，例如 example.com"; return 1; }
    grep -qxF "$d" "$WHITELIST" 2>/dev/null && { colorEcho "$YELLOW" "${d} 已在白名单里"; return 0; }
    candidate=$(mktemp)
    [[ ! -f "$WHITELIST" ]] || cp "$WHITELIST" "$candidate"
    echo "$d" >> "$candidate"
    commit_whitelist "$candidate" && colorEcho "$GREEN" "✓ 已添加 ${d}"
}
wl_remove() {
    local d candidate
    d=$(normalize_domain "$1")
    valid_domain "$d" || { colorEcho "$RED" "域名格式不对"; return 1; }
    grep -qxF "$d" "$WHITELIST" 2>/dev/null || { colorEcho "$YELLOW" "${d} 不在白名单里"; return 1; }
    candidate=$(mktemp)
    grep -vxF "$d" "$WHITELIST" > "$candidate" || { [[ $? -eq 1 ]] || { rm -f "$candidate"; return 1; }; }
    commit_whitelist "$candidate" && colorEcho "$GREEN" "✓ 已删除 ${d}"
}
wl_reset() {
    local candidate; candidate=$(mktemp)
    echo "$DEFAULT_DOMAINS" | tr ' ' '\n' > "$candidate"
    commit_whitelist "$candidate" && colorEcho "$GREEN" "✓ 已恢复默认白名单"
}
wl_clear() {
    local candidate; candidate=$(mktemp)
    commit_whitelist "$candidate" && colorEcho "$GREEN" "✓ 已清空白名单：现在不放行任何目标"
}
wl_list() { if [[ -s "$WHITELIST" ]]; then nl -w2 -s'. ' "$WHITELIST"; else echo "(空 — 不放行任何目标)"; fi; }

whitelist_cmd() {
    case "${1:-}" in
        list|"") wl_list ;;
        add) [[ -n "${2:-}" ]] || { echo "用法: huarun whitelist add 域名"; return 1; }; wl_add "$2" ;;
        remove|rm|del) [[ -n "${2:-}" ]] || { echo "用法: huarun whitelist remove 域名"; return 1; }; wl_remove "$2" ;;
        reset)
            require_terminal || return 1
            read -r -p "覆盖为默认白名单，输入 YES 确认: " confirm
            [[ "$confirm" == "YES" ]] || { echo "已取消"; return 1; }
            wl_reset ;;
        clear) require_terminal || return 1; [[ "${2:-}" == "--yes" ]] || { colorEcho "$YELLOW" "清空白名单后将阻止所有隧道目标。确认请用：huarun whitelist clear --yes"; cat /usr/local/etc/xray/TOS.txt 2>/dev/null; return 1; }; wl_clear ;;
        *) echo "用法: huarun whitelist list|add 域名|remove 域名|reset|clear --yes" ;;
    esac
}

whitelist_menu() {
    while true; do
        echo ""; echo -e "${BLUE}白名单管理${PLAIN}"; echo ""
        echo "当前白名单："; wl_list
        echo ""
        echo "  a. 添加域名"
        echo "  d. 删除域名"
        echo "  r. 全部删除（阻止全部目标）"
        echo "  s. 恢复默认白名单"
        echo "  0. 返回主菜单"
        echo ""
        read -r -p "请选择: " wl_choice
        case $wl_choice in
            a) read -r -p "请输入域名（例如 example.com）: " nd; [[ -n "$nd" ]] && wl_add "$nd" ;;
            d) read -r -p "请输入要删除的域名: " nd; [[ -n "$nd" ]] && wl_remove "$nd" ;;
            r)
                echo ""; colorEcho "$RED" "即将删除所有白名单条目，之后阻止全部目标。"; cat /usr/local/etc/xray/TOS.txt 2>/dev/null
                echo ""; read -r -p "输入 YES 确认，其他任意键取消: " confirm
                [[ "$confirm" == "YES" ]] && wl_clear || colorEcho "$YELLOW" "已取消" ;;
            s) read -r -p "恢复为出厂默认白名单（$(wc -w <<< "$DEFAULT_DOMAINS") 个根域名），确认？(y/n) " confirm; [[ "$confirm" =~ ^[yY]$ ]] && wl_reset ;;
            0) return 0 ;;
            *) colorEcho "$RED" "无效选项" ;;
        esac
    done
}

# 子命令：给助手和自动化用；不带参数进菜单
manager_main() {
case "${1:-}" in
    status)    show_status "${2:-}" ;;
    doctor)    run_doctor "${2:-}" ;;
    fix)       do_fix ;;
    info)      show_info "${2:-}" ;;
    logs)      view_logs "${2:-30}" ;;
    renew)     renew_cert ;;
    update)    update_xray ;;
    render)    render_site && echo "ok" ;;
    restart)   restart_services ;;
    whitelist) shift; whitelist_cmd "$@" ;;
    chat)      shift; chat "$@" ;;
    assistant) shift; assistant_cmd "$@" ;;
    uninstall) uninstall "${2:-}" ;;
    version)   echo "$VERSION" ;;
    help|-h|--help)
        cat <<H
用法: huarun [子命令]
  status [--json]      服务、端口、证书、续期、助手
  doctor [--json]      体检，每项 ok/false 带提示
  fix                  按顺序自动修：配置、防火墙、续期任务、证书、服务
  info [--json]        连接信息（vmess 链接）
  logs [行数]          xray 和 nginx 日志
  renew / update       手动续期证书 / 更新 Xray 内核
  whitelist list|add 域名|remove 域名|reset|clear --yes
  chat                 跟 AI 助手说话
  assistant setup|remove
  uninstall [--yes]
不带参数进菜单。
H
        ;;
    *)         show_menu ;;
esac
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then manager_main "$@"; fi
MGRSCRIPT
    # 出厂白名单只在脚本顶上定义一次，这里填进管理命令
    sed -i "s|^DEFAULT_DOMAINS=\"__DEFAULT_DOMAINS__\"|DEFAULT_DOMAINS=\"${DEFAULT_DOMAINS}\"|" /usr/local/bin/huarun
    grep -q '^DEFAULT_DOMAINS="google.com ' /usr/local/bin/huarun || { say "$RED" "✗ 管理命令里的默认白名单没写进去"; exit 1; }
    chmod +x /usr/local/bin/huarun
    say "$GREEN" "✓ 管理命令已安装: huarun"
}

#=== 主流程 ==================================================================
main() {
    set -e
    parseArgs "$@"
    checkSystem
    checkConflicts
    askKey
    getData
    PICO_TMP=""
    trap '[[ -z "${PICO_TMP:-}" ]] || rm -rf -- "$PICO_TMP"; unset AI_KEY HUARUN_API_KEY' EXIT
    prepareAssistant
    preflight
    vps_check

    say "$BLUE" ""; say "$BLUE" "备份已有配置..."
    mkdir -p /etc/huarun/backup 2>/dev/null || true
    [[ -f /usr/local/etc/xray/config.json ]] && cp /usr/local/etc/xray/config.json "/etc/huarun/backup/config.json.bak.$(date +%s)" 2>/dev/null || true
    [[ -f /etc/nginx/conf.d/huarun.conf ]] && cp /etc/nginx/conf.d/huarun.conf "/etc/huarun/backup/huarun.conf.bak.$(date +%s)" 2>/dev/null || true

    installDeps
    installXray
    openFirewall
    installCert
    generateConfig
    installTemplates
    enableBBR
    setupWhitelist
    saveInfo
    installManager
    installAssistantTemplate
    /usr/local/bin/huarun render >/dev/null && say "$GREEN" "✓ 站点首页已生成"
    startServices
    installAssistant
    showInfo
    if [[ -n "$AI_KEY" && -f "${AI_HOME}/config.json" && $OPT_JSON -eq 0 && -t 0 ]]; then
        echo ""
        colorEcho "$BLUE" "装好了。现在可以直接跟助手说话（输入 exit 退出；以后 ssh 上来输 huarun chat）："
        [[ -z "${PICO_TMP:-}" ]] || rm -rf -- "$PICO_TMP"
        unset AI_KEY HUARUN_API_KEY
        exec /usr/local/bin/huarun chat
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then main "$@"; fi
