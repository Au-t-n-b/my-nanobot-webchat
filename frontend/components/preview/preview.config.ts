export const PREVIEW_LIMITS = {
  /** ZIP: 最大构树条目数，避免 DOM 爆炸 */
  MAX_ZIP_ENTRIES: 1000,
  /** ZIP: 单 entry 最大可解压字节数，避免 OOM（10MB） */
  MAX_ZIP_ENTRY_BYTES: 10 * 1024 * 1024,

  /** 结构化预览：最大行数 */
  MAX_GRID_ROWS: 1000,
  /** 结构化预览：最大列数 */
  MAX_GRID_COLS: 50,
  /** 文本解析兜底：最大可解析字节数（5MB） */
  MAX_PARSE_BYTES: 5 * 1024 * 1024,

  /** ZIP 树：当文件数超过该值时展示搜索框 */
  ZIP_SEARCH_THRESHOLD_FILES: 15,
} as const;

