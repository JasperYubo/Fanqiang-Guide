const escape = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

function browserApp(config) {
  const $ = id => document.getElementById(id);
  const names = { dns: 'DNS 解析', tcp: 'TCP 连接', tls: 'TLS 握手', http: 'HTTPS 响应', throughput: '受限下载测速' };
  const phaseNames = { idle: '准备开始', running: '正在诊断', stopping: '正在停止', complete: '诊断完成', stopped: '已停止', error: '本次未完成', review: '等待你决定', submitting: '正在提交', submitted: '已收到回执', deleting: '正在删除远程报告', remote_deleted: '远程报告已删除' };
  const errors = {
    busy: '当前操作尚未结束，请稍后重试。',
    preview_required: '报告已变化，请重新预览后再提交。',
    submission_pending: '上次提交结果尚未确认。请用同一份预览重试，以找回回执。',
    submission_uncertain: '未确认是否收到报告。请重试提交；同一份报告会使用同一请求标识，避免重复保存。',
    delete_remote_first: '请先删除已提交的远程报告，再开始新一轮。',
    budget_exhausted: '本次会话的流量额度已用完。',
    delete_failed: '未确认远程删除成功，请稍后重试。',
    report_not_ready: '请先完成或停止本次诊断。',
    invalid_log: '日志太长。请只粘贴与报错有关的短片段。',
    diagnostic_failed: '诊断未能完成。没有把失败值当成零。',
    cancelled: '本次诊断已停止。',
    local_error: '本地操作未完成，请重试。',
    delete_local_first: '请先删除当前未提交的本地报告，再恢复历史回执。',
    nothing_to_restore: '没有可恢复的未决提交或回执。'
  };
  let state = null;
  let grant = null;
  let pending = false;
  let polling = false;
  let logsChanged = false;
  let logsVersion = 0;
  let logsQueue = Promise.resolve();
  function notice(text, bad = false) {
    $('notice').textContent = text;
    $('notice').className = bad ? 'notice bad' : 'notice';
  }
  async function api(route, body) {
    const response = await fetch(config.basePath + 'api/' + route, {
      method: body === undefined ? 'GET' : 'POST',
      headers: body === undefined ? { 'X-session': config.sessionKey } : { 'X-session': config.sessionKey, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'omit', cache: 'no-store', redirect: 'error'
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || 'local_error');
    return value;
  }
  function clearPreview() {
    grant = null;
    $('review').hidden = true;
    $('submit').disabled = true;
  }
  function number(value, unit) { return value === null || value === undefined ? '未测' : Number(value).toFixed(1) + ' ' + unit; }
  function render(value) {
    state = value;
    $('phase').textContent = phaseNames[value.phase] || '等待操作';
    $('used').textContent = (value.session_budget.used_payload_bytes / 1048576).toFixed(2) + ' / 20 MiB';
    const active = ['running', 'stopping', 'submitting', 'deleting'].includes(value.phase);
    $('start').disabled = pending || !value.can_start;
    $('throughput').disabled = active || pending;
    $('problem').disabled = active || pending;
    $('stop').disabled = !['running', 'stopping'].includes(value.phase);
    $('logs').disabled = active || pending || !!value.receipt && !value.receipt.deleted_at || value.submission_pending;
    $('preview').disabled = pending || active || !value.has_report || !!value.receipt && !value.receipt.deleted_at;
    $('delete-local').disabled = active || pending || value.submission_pending || !!value.receipt && !value.receipt.deleted_at || !value.has_report && !value.receipt;
    $('restore').disabled = pending || !value.can_restore;
    $('remote-delete').disabled = pending || active || !value.receipt || !!value.receipt.deleted_at;
    const p = value.progress;
    $('progress-label').textContent = p ? (names[p.stage] || '诊断') + ' · ' + p.completed + ' / ' + p.total : '等待开始';
    $('progress').max = p?.total || 1;
    $('progress').value = p?.completed || 0;
    if (grant && value.preview_sha256 !== grant.preview_sha256) clearPreview();
    $('submit').disabled = pending || active || !grant || logsChanged || !!value.receipt;
    $('receipt-box').hidden = !value.receipt;
    if (value.receipt) {
      $('receipt-id').textContent = value.receipt.receipt_id;
      $('receipt-time').textContent = value.receipt.received_at;
      $('receipt-expiry').textContent = value.receipt.expires_at;
      $('receipt-state').textContent = value.receipt.deleted_at ? '已删除或服务器已无此报告' : '仅用于问题排查，不公开';
    }
    $('empty').hidden = value.has_report;
  }
  async function refresh() {
    if (polling) return;
    polling = true;
    try { render(await api('status')); }
    catch (e) { notice(errors[e.message] || '本地连接已关闭。可以关闭此页面。', true); }
    finally { polling = false; }
  }
  async function action(fn) {
    if (pending) return;
    pending = true;
    if (state) render(state);
    try { await fn(); }
    catch (e) { notice(errors[e.message] || '操作未完成，请重试。', true); }
    finally { pending = false; await refresh(); }
  }
  $('start').addEventListener('click', () => action(async () => {
    await logsQueue;
    clearPreview();
    $('logs').value = '';
    $('redacted-log').textContent = '尚未粘贴日志。';
    logsChanged = false;
    const value = await api('start', { throughput: $('throughput').checked, problem_category: $('problem').value });
    render(value);
    notice('正在本机诊断。你可以随时停止；不会上传结果。');
  }));
  $('stop').addEventListener('click', () => action(async () => {
    render(await api('stop', {}));
    notice('已请求停止；保留已经完成的测量。');
  }));
  $('logs').addEventListener('input', () => {
    clearPreview();
    logsChanged = true;
    const version = ++logsVersion;
    const text = $('logs').value;
    logsQueue = logsQueue.catch(() => {}).then(async () => {
      const value = await api('logs', { text });
      if (version === logsVersion) {
        $('redacted-log').textContent = value.text || '没有日志内容。';
        $('log-categories').textContent = value.categories.length ? '已处理：' + value.categories.join('、') : '未识别到预设类别；请自行检查敏感内容。';
        logsChanged = false;
        render(value.status);
      }
    }).catch(e => { notice(errors[e.message] || '日志预览未完成，请重试。', true); throw e; });
    // Keep errors handled even when the user never clicks preview.
    logsQueue.catch(() => {});
  });
  $('preview').addEventListener('click', () => action(async () => {
    await logsQueue;
    if (logsChanged) throw new Error('preview_required');
    const value = await api('preview', {});
    grant = value;
    $('report-json').textContent = JSON.stringify(value.report, null, 2);
    $('digest').textContent = value.preview_sha256;
    $('destination').textContent = value.destination;
    const summary = value.report.summary;
    $('tcp-ms').textContent = number(summary.tcp_median_ms, 'ms');
    $('http-ms').textContent = number(summary.http_median_ms, 'ms');
    $('download').textContent = number(summary.download_mbps, 'Mbps');
    $('failure').textContent = summary.tcp_failure_ratio === null ? '未测' : (summary.tcp_failure_ratio * 100).toFixed(1) + '%';
    $('review').hidden = false;
    notice('下面就是将提交的完整报告。日志全文不会提交。你也可以直接关闭页面，不提交。');
    $('review').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
  $('submit').addEventListener('click', () => action(async () => {
    if (!grant || logsChanged) throw new Error('preview_required');
    const value = await api('submit', { preview_sha256: grant.preview_sha256, preview_token: grant.preview_token });
    render(value.status);
    notice('报告已提交，删除凭据保存在本机。可以随时删除远程报告。');
  }));
  $('remote-delete').addEventListener('click', () => action(async () => {
    const value = await api('remote-delete', {});
    render(value.status);
    notice('远程报告已删除，或服务器上已不存在此报告。本地报告仍保留。');
  }));
  $('delete-local').addEventListener('click', () => action(async () => {
    await logsQueue.catch(() => {});
    render(await api('local-delete', {}));
    clearPreview();
    $('logs').value = '';
    $('redacted-log').textContent = '本地日志预览已清空。';
    $('log-categories').textContent = '';
    logsChanged = false;
    notice('本轮本地报告与回执已删除。此操作不会删除远程报告。');
  }));
  $('restore').addEventListener('click', () => action(async () => {
    const value = await api('restore', {});
    clearPreview();
    render(value);
    notice(value.receipt ? '已恢复最近一份回执，没有发送网络请求。可主动删除远程报告。' : '已恢复同一份未决报告。请重新预览后重试提交；会沿用原请求编号。');
  }));
  $('exit').addEventListener('click', () => {
    notice('可以直接关闭此标签页；未点击提交就不会上传。要停止本地程序，请回到启动它的终端或 MCP 客户端。');
    window.close();
  });
  refresh();
  const timer = setInterval(refresh, 750);
  window.addEventListener('pagehide', () => clearInterval(timer));
}

export function renderUiPage({ nonce, sessionKey, basePath, target, executionLocation }) {
  const config = JSON.stringify({ sessionKey, basePath }).replace(/</g, '\\u003c').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  const location = executionLocation === 'linux_lab' ? 'Linux 实验室 · 测量发生在服务器' : '本机诊断 · 测量发生在当前运行程序的设备';
  return [
    '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>网络诊断 · 翻墙与科学上网工具指南</title>',
    '<style nonce="' + escape(nonce) + '">',
    ':root{font-family:system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;color:#12212c;background:#f1f5f7;font-size:16px;line-height:1.65}*{box-sizing:border-box}body{margin:0}button,input,select,textarea{font:inherit}button{cursor:pointer;border:1px solid #c8d6df;border-radius:11px;padding:10px 17px;background:white;color:#183445;font-weight:650}button:hover:not(:disabled){background:#e9f3fa;border-color:#82a9c5}button:disabled{cursor:not-allowed;opacity:.45}button.primary{background:#164e71;color:#fff;border-color:#164e71}button.primary:hover:not(:disabled){background:#103b56}button.danger{color:#a12e2e}.top{background:#102e42;color:#f7fbff;border-bottom:5px solid #47bcb4}.top-inner{max-width:1120px;margin:auto;padding:35px 28px 30px}.eyebrow{letter-spacing:.08em;font-size:12px;color:#a7c4d8;font-weight:700}.top h1{font-size:34px;letter-spacing:-.03em;line-height:1.2;margin:12px 0}.top p{color:#c5d9e6;max-width:760px;margin:0}.badge{display:inline-block;border:1px solid #567789;border-radius:30px;padding:4px 11px;margin-top:18px;font-size:13px}main{max-width:1120px;margin:25px auto;padding:0 28px 45px}.layout{display:grid;grid-template-columns:1.18fr 1fr;gap:22px}.card{background:#fff;border:1px solid #d8e2e8;border-radius:18px;padding:25px;margin-bottom:22px;box-shadow:0 3px 12px #16384c05}.card h2{font-size:20px;line-height:1.4;margin:0 0 15px}.step{display:inline-grid;place-items:center;width:29px;height:29px;border-radius:9px;background:#e4f1f2;color:#176a65;font-size:14px;margin-right:9px}.muted{color:#617581;font-size:14px}.facts{display:grid;grid-template-columns:112px 1fr;gap:10px;font-size:14px}.facts dt{color:#617581}.facts dd{margin:0;overflow-wrap:anywhere}.note{border-left:3px solid #6c9db6;padding:9px 12px;background:#f2f7fa;font-size:14px;margin:16px 0}.notice{background:#e7f4ef;color:#285b49;border:1px solid #c3dfd1;border-radius:12px;padding:13px 17px;margin-bottom:22px;overflow-wrap:anywhere}.notice.bad{background:#fff0ea;color:#88462e;border-color:#edc5b4}.field{display:block;margin:16px 0 7px;font-weight:600;font-size:14px}select,textarea{border:1px solid #beced8;background:white;color:#203846;border-radius:9px;padding:10px;width:100%}textarea{resize:vertical;min-height:135px;font-family:ui-monospace,monospace;font-size:13px;line-height:1.6}label.check{display:flex;gap:11px;align-items:flex-start;padding:14px;border:1px solid #d7e4e9;border-radius:11px;margin:18px 0;font-size:14px}input[type=checkbox]{width:19px;height:19px;margin:3px 0;accent-color:#176986}.buttons{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:18px}.separator{border:0;border-top:1px solid #e2e9ed;margin:22px 0}.status-line{display:flex;justify-content:space-between;gap:14px;align-items:center;font-size:14px}#phase{font-size:19px;font-weight:700}progress{width:100%;height:11px;accent-color:#218c8c;margin:14px 0 4px}pre{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;line-height:1.65;background:#f5f8fa;border:1px solid #dee7eb;padding:15px;border-radius:10px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:420px;overflow:auto}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin:20px 0}.metric{background:#edf5f6;border-radius:12px;padding:16px}.metric span{display:block;font-size:12px;color:#56717d}.metric strong{font-size:21px;font-weight:650}.wide{grid-column:1/-1}.hash{font-family:ui-monospace,monospace;font-size:11px;overflow-wrap:anywhere}details summary{cursor:pointer;font-weight:600}.fine{font-size:12px;color:#667b88}.footer{font-size:12px;color:#617581}a{color:#176986}button:focus-visible,select:focus-visible,textarea:focus-visible,input:focus-visible{outline:3px solid #86c9e2;outline-offset:3px}[hidden]{display:none!important}@media(max-width:760px){.layout{grid-template-columns:1fr}.top-inner{padding:27px 20px}main{padding:0 16px 30px;margin-top:18px}.top h1{font-size:28px}.card{padding:20px}.metrics{grid-template-columns:1fr 1fr}.facts{grid-template-columns:92px 1fr}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}',
    '</style></head><body><header class="top"><div class="top-inner"><div class="eyebrow">FANQIANG.GUIDE / DIAGNOSTICS</div><h1>先看清问题，再决定是否分享</h1><p>分开检查解析、连接与响应。数据先留本地，预览后由你选择提交；不会自动更改网络设置。</p><span class="badge">' + escape(location) + '</span></div></header>',
    '<main><div id="notice" class="notice" role="status" aria-live="polite">尚未开始，没有上传任何报告。</div><div class="layout">',
    '<section class="card"><h2><span class="step">1</span>确认本次诊断</h2><dl class="facts"><dt>固定目标</dt><dd>fanqiang.guide：DNS、TCP 443、TLS、HTTPS 小响应；可选受限下载。</dd><dt>路由方式</dt><dd>只测系统路由／TUN 路径；不自动使用 HTTP、SOCKS 或应用代理，不代表某个应用的代理效果。</dd><dt>流量与时长</dt><dd>每次 HTTP 响应体 ≤ 10 MiB、最长 15 秒；本会话累计 ≤ 20 MiB。协议开销另计。</dd><dt>结果范围</dt><dd>固定目标的小样本；TCP 失败率不是 ICMP 丢包率，下载结果不是峰值带宽。</dd></dl>',
    '<details class="note"><summary>测量方法与边界</summary><p>DNS 查询系统配置的 DNS 服务器，分别请求 A／AAAA；不等同于浏览器 DoH、hosts 或系统 NSS 解析。</p><p>TLS 耗时包含新建 TCP 连接；HTTPS 为新连接的总耗时。流量预算只统计 HTTP 响应体字节，不含协议开销。此处不测 ICMP 丢包，也不能证明宽带或节点峰值速度。</p></details><label class="field" for="problem">你遇到的主要问题</label><select id="problem"><option value="connectivity">连接失败</option><option value="slow">访问慢</option><option value="dns">解析问题</option><option value="application">应用报错</option><option value="other">其他 / 尚不确定</option></select>',
    '<label class="check"><input type="checkbox" id="throughput"><span><strong>同时进行受限下载测速</strong><br><span class="muted">默认关闭。不上传测速文件；计量网络请留意流量。停止后保留已有结果。</span></span></label><div class="buttons"><button id="start" class="primary">开始本地诊断</button><button id="stop" disabled>停止</button></div><div class="note">首版先桌面：Linux 已用于开发验证，其他桌面按实际测试提供。iPhone / iOS 暂用手工采集或主动导出；远程 MCP 无法直接测试 iPhone 上的微信等应用。</div></section>',
    '<section class="card"><h2>本次进度</h2><div class="status-line"><span id="phase">准备开始</span><span id="used" class="muted">0 / 20 MiB</span></div><progress id="progress" max="1" value="0" aria-label="当前步骤进度"></progress><div id="progress-label" class="muted">等待开始</div><p id="empty" class="muted">尚无测量数据。未测项目会保留为 null，不会被填成 0。</p><hr class="separator"><h2><span class="step">2</span>可选：本地查看报错</h2><label class="field" for="logs">粘贴相关日志片段</label><textarea id="logs" maxlength="16000" placeholder="可留空。不要粘贴完整配置、订阅或聊天记录。" autocomplete="off" spellcheck="false"></textarea><p class="muted">全文只在本地处理，脱敏后的全文也不会提交。此工具不会读取全机日志。</p><details><summary>查看本地脱敏预览</summary><pre id="redacted-log">尚未粘贴日志。</pre><p id="log-categories" class="fine"></p></details><div class="buttons"><button id="preview" class="primary" disabled>预览完整报告</button><button id="exit">不提交，退出</button></div></section>',
    '<section class="card wide" id="review" hidden><h2><span class="step">3</span>确认这份报告，再提交</h2><p class="muted">只包含软件版本、执行位置与平台、固定问题类别、测量样本、摘要、预算及脱敏类别。没有日志全文、用户名、IP、订阅或节点信息。</p><div class="metrics"><div class="metric"><span>TCP 中位耗时</span><strong id="tcp-ms">未测</strong></div><div class="metric"><span>HTTPS 中位耗时</span><strong id="http-ms">未测</strong></div><div class="metric"><span>TCP 连接失败率</span><strong id="failure">未测</strong></div><div class="metric"><span>受限下载</span><strong id="download">未测</strong></div></div><dl class="facts"><dt>提交目的地</dt><dd id="destination">' + escape(target + '/v1/reports') + '</dd><dt>用途与保留</dt><dd>用于问题排查，最多保留 30 天；不公开，不进入 GA4。公开案例需要将来另行预览并明确选择。</dd><dt>预览指纹</dt><dd id="digest" class="hash"></dd></dl><h3>将提交的全部内容</h3><pre id="report-json" tabindex="0"></pre><p class="fine">修改日志或重新测试会使这份预览失效。格式校验只说明字段合法，不能证明测量真实。</p><div class="buttons"><button id="submit" class="primary" disabled>提交上面这份报告</button><span class="muted">没有点击此按钮，就不会提交。</span></div></section>',
    '<section class="card wide" id="receipt-box" hidden><h2>提交回执</h2><dl class="facts"><dt>回执编号</dt><dd id="receipt-id"></dd><dt>收到时间</dt><dd id="receipt-time"></dd><dt>到期时间</dt><dd id="receipt-expiry"></dd><dt>当前状态</dt><dd id="receipt-state"></dd></dl><p class="muted">删除凭据保存在本机的私有回执文件中，不会写入 MCP 日志。</p><div class="buttons"><button id="remote-delete" class="danger">删除远程报告</button></div></section>',
    '</div><section class="card"><h2>本地数据由你管理</h2><p class="muted">本机只保存本轮报告与回执，不保存粘贴的日志。未决提交须先重试确认回执；已提交的报告须先删除远程副本，才能清除本地回执。重启后可恢复最近一份未决提交或回执；恢复本身不会访问网络。</p><div class="buttons"><button id="restore" disabled>恢复最近一份提交或回执</button><button id="delete-local" class="danger" disabled>删除本轮本地报告与回执</button></div></section><footer class="footer">网络诊断 v0.1 · 无 GA4 · 不自动修复 · 不自动公开案例</footer></main>',
    '<script nonce="' + escape(nonce) + '">(' + browserApp.toString() + ')(' + config + ');</script></body></html>'
  ].join('\n');
}
