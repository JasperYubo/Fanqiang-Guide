// Synthetic test data only. Must never be compiled into a deployed Worker.
export const fixture = (overrides = {}) => ({
  schema_version: 1,
  entity_aliases: { v2rayn: ['v2rayN'], v2rayng: ['v2rayNG'] },
  entries: [{
    faq_id: 'synthetic-download', question_id: 'synthetic-q1', generation_key: 'synthetic-generation',
    canonical_question: 'v2rayN 从哪里下载？', aliases: ['下载 v2rayN', 'v2rayN下载'], intent: 'download',
    entities: ['v2rayn'], platforms: ['windows'], version_constraints: [], hardware_constraints: [],
    required_slots: ['platform', 'entity'], forbidden_mismatch: [],
    short_answer: '测试参考：请从经过核对的项目发行页获取下载资料。', answer_sections: [{ title: '适用范围', content: '测试资料仅适用于本条记录明确的系统。' }],
    source_ids: ['synthetic-source'], sources: [], source_claim_map: { short_answer: ['synthetic-source'] },
    dynamic_class: 'stable', checked_at_utc: '2026-09-01T00:00:00Z', expires_at_utc_or_null: null,
    origin_kind: 'google_autocomplete_editorial_faq', review_state: 'approved', cache_eligible: true,
    ...overrides,
  }],
  sources: [{ source_id: 'synthetic-source', title: '测试发行页', url: 'https://example.com/release', verification_status: 'verified', checked_at_utc: '2026-09-01T00:00:00Z', content_sha256: 'a'.repeat(64) }],
});
export const flow = (overrides = {}) => ({ aiReady: true, aiTool: 'DeepSeek', originalRequest: '下载 v2rayN', device: 'Windows 11 电脑', need: '下载 v2rayN', details: [], ...overrides });
