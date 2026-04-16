# USPTO Global Dossier — 页面结构与操作参考

## 网站信息
- 首页：https://globaldossier.uspto.gov/home
- 档案详情页格式：`https://globaldossier.uspto.gov/details/{OFFICE}/{APP_NUM}/{TYPE}/{ID}`
  - 例：`https://globaldossier.uspto.gov/details/CN/202211613450/A/106642`

## 搜索表单元素

| 元素 | ID/选择器 | 说明 |
|------|-----------|------|
| Office 下拉框 | `#country` | 选项文本：US / CN / EP / KR / JP / WIPO / CASE |
| Type 下拉框 | `#type` | 选项文本：Application / Pre-grant Publication / Patent |
| 申请号输入框 | `#query` | 原始 pattern 限制 8 位，CN 12 位号需 removeAttribute('pattern') |
| 搜索按钮 | `button[name="search"]` | 所有字段填完才会 enabled |

## 重要操作注意事项

### CN 申请号格式
- CN 专利申请号为 12 位数字，如 `202211613450`
- 页面原始 input pattern 限制 8 位，必须先用 JS 移除：
  ```javascript
  document.getElementById('query').removeAttribute('pattern');
  document.getElementById('query').removeAttribute('maxlength');
  ```

### 页面等待策略
- 首页加载：`wait_until="domcontentloaded"` + 4000ms
- 搜索结果跳转：轮询 `page.url` 直到包含 `result/` 或 `details/`，最多 30 秒
- 档案详情页渲染：`wait_until="domcontentloaded"` + 7000ms（Angular SPA 需要额外等待）

## 档案页面结构

详情页包含以下标签视图（通过按钮切换）：
- **All Docs**（默认）：所有提交文件的完整列表，含日期和文件名
- **Patent Fam.**：专利家族状态，含各成员申请状态
- **Class. & Citation**：分类号和引用文献

### All Docs 文档列表格式
页面文本中，文档条目大致格式：
```
<文件名>
<日期 YYYY/MM/DD>
Download   View
```

## 同族链接提取

家族列表页 HTML 中，View Dossier 链接格式：
```html
<a href="details/KR/20170012160/A/121383">
  View Dossier <span class="sr-only">for application id 121383</span>
</a>
```

路径规律：`details/{OFFICE}/{APP_NUM}/{APP_TYPE}/{GD_ID}`
- APP_TYPE: A=Application, W=PCT

## 常见 Office 代码含义

| 代码 | 专利局 |
|------|--------|
| CN | 中国国家知识产权局（CNIPA） |
| KR | 韩国特许厅（KIPO） |
| US | 美国专利商标局（USPTO） |
| EP | 欧洲专利局（EPO） |
| JP | 日本特许厅（JPO） |
| WIPO | 世界知识产权组织（PCT） |

## 审查状态关键词识别

### CNIPA (CN)
- `授权` / `patent granted` → 已授权
- `驳回` / `rejected` → 已驳回
- `撤回` / `withdrawn` → 已撤回
- `补充检索` / `supplementary search` → 补充检索完成，等待 OA
- `第一次审查意见` / `office action` → 审查意见待复审

### KIPO (KR)
- `registration` / `registered` → 已授权
- `final rejection` → 最终驳回
- `office action` → 审查意见待复审

### EPO (EP)
- `granted` → 已授权
- `examination report` → 审查报告已发出

### PCT (WIPO)
- `iprp` / `chapter ii` → IPRP 已发出，PCT 程序完结
- `chapter i` → 国际检索/初步审查完成
