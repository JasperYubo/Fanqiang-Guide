def add_official_docs(P):
    html='''<section class="section wrap" id="official-docs"><div class="section-heading"><div><p class="eyebrow">官方资料</p><h2>Xray 与 sing-box 官方教程和配置文档</h2></div></div><div class="quick-answers"><article class="quick-answer"><h3><a href="https://xtls.github.io/">Xray 官方中文文档 ↗</a></h3><p>快速入门、配置指南、入门与进阶技巧，以及 VLESS、REALITY 等技术资料。</p></article><article class="quick-answer"><h3><a href="https://sing-box.sagernet.org/">sing-box 官方文档 ↗</a></h3><p>客户端、服务端、DNS、路由和配置迁移说明，适合查配置与排错；站内可切换简体中文。</p></article></div><p class="section-note">资料核对：2026-09-13。配置字段与版本变化以对应官方文档为准。</p></section>'''
    md='''## Xray 与 sing-box 官方教程和配置文档

- [Xray 官方中文文档](https://xtls.github.io/)：快速入门、配置指南、入门与进阶技巧，以及 VLESS、REALITY 等技术资料。
- [sing-box 官方文档](https://sing-box.sagernet.org/)：客户端、服务端、DNS、路由和配置迁移说明，适合查配置与排错；站内可切换简体中文。

资料核对：2026-09-13。配置字段与版本变化以对应官方文档为准。

'''
    p=P/'index.html';text=p.read_text(encoding='utf-8')
    assert 'id="official-docs"' not in text
    marker='<section class="section wrap" id="answers">'
    assert marker in text
    p.write_text(text.replace(marker,html+marker,1),encoding='utf-8')
    p=P/'index.md';text=p.read_text(encoding='utf-8')
    marker='## 科学上网工具常见问题'
    assert marker in text
    p.write_text(text.replace(marker,md+marker,1),encoding='utf-8')
    p=P/'sitemap.xml';text=p.read_text(encoding='utf-8')
    for url in ('https://fanqiang.guide/','https://fanqiang.guide/ai/','https://fanqiang.guide/guides/proxy-cores.html'):
        old='<loc>'+url+'</loc><lastmod>2026-09-13</lastmod>'
        assert old in text
        text=text.replace(old,'<loc>'+url+'</loc><lastmod>2026-09-13</lastmod>',1)
    p.write_text(text,encoding='utf-8')
