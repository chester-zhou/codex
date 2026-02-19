# 飞利浦医疗售后服务新闻检索记录（近一个月）

- 检索日期：2026-02-19
- 目标时间窗：2026-01-19 至 2026-02-19
- 检索范围：中英文网站
- 关键词：
  - 中文：飞利浦 医疗 售后 服务、飞利浦 医疗 服务 合同、飞利浦 医疗 维修
  - 英文：Philips Healthcare after-sales service、Philips service contract、Philips field service

## 执行记录

1. 尝试访问 Google News RSS（英文/中文关键词）
   - 结果：代理隧道返回 `403 Forbidden`
2. 尝试访问 Reuters 站点验证外网连通性
   - 结果：代理隧道返回 `403 Forbidden`

## 结论

当前运行环境无法访问公开互联网新闻站点，因此无法在本环境内给出“近一个月”的真实新闻条目清单。

## 如何解决外网被代理拦截问题

> 目标：把“代理能通”与“目标站可访问”分开排查，优先恢复只读抓取能力。

### 1) 先确认代理变量是否配置正确

在终端检查：

- `env | grep -i proxy`

重点核对：

- `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` 是否存在且地址正确
- `NO_PROXY` 是否错误包含了外网域名（会导致请求绕过代理并失败）

### 2) 用最小化命令测试代理链路

- `curl -I https://example.com`
- `curl -I https://news.google.com`

若都报 `CONNECT tunnel failed, response 403`，通常表示：

- 代理账号无权限（ACL 拒绝）
- 代理策略禁止目标域名类别（新闻、海外媒体等）
- 代理要求认证，但当前进程未带认证信息

### 3) 明确代理认证方式并补齐凭据

常见方式：

- 用户名密码：`http://user:pass@proxy-host:port`
- IP 白名单：需要把当前出口 IP 加白
- SSO/短期令牌：需定期刷新 token

若公司不允许在环境变量中放明文密码，可使用：

- CI Secret / Vault 注入
- 临时会话 token
- 只读专用代理账号（最小权限）

### 4) 把目标新闻站加入白名单（最关键）

向网络/安全团队提交白名单申请时，建议一次性附上：

- 用途：舆情与行业公开信息抓取（只读）
- 域名清单（示例）：
  - `news.google.com`
  - `www.reuters.com`
  - `www.philips.com`
  - `www.fda.gov`
- 协议与端口：`HTTPS/443`
- 访问频率：低频（如每小时 1~2 次）

### 5) 技术兜底方案（白名单未开通前）

- 使用企业已允许的新闻数据源（内部数据中台/第三方聚合 API）
- 在可联网跳板机定时抓取后，产出结构化 JSON 再同步到当前环境
- 通过人工导出 RSS/CSV 后导入分析流程

### 6) 推荐排查顺序（30 分钟内）

1. 检查代理变量与凭据是否过期
2. `curl -I https://example.com` 验证基础连通
3. `curl -I` 测试业务目标域名
4. 若仅目标域名失败，提交白名单工单并附错误日志
5. 临时改用可访问数据源，保证日报不中断

## 建议的人工检索清单（可在可联网环境执行）

- 中文站点：
  - 飞利浦中国新闻中心（医疗业务）
  - 医疗器械行业媒体（如健康界、器械之家等）
  - 国家药监局/NMPA 相关公告（如涉及售后整改、召回与服务通知）
- 英文站点：
  - Philips global newsroom
  - FDA recalls / field safety notices（如涉及服务与售后执行）
  - Reuters / MedTechDive / Fierce Biotech（行业报道）

## 可复用查询语句

- `("飞利浦" AND "医疗" AND ("售后" OR "服务" OR "维保")) AND 日期:近30天`
- `("Philips" AND ("Healthcare" OR "medical" ) AND ("after-sales" OR "service" OR "maintenance")) AND past month`
